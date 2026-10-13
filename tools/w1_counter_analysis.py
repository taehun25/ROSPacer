"""Freeze training-only counter calibration; evaluate unclipped held-out residuals.

The empirical relay curve is a candidate for UDP1400/iperf1ms on one AP,
not a universal physical airtime model or an approval of normal adaptive.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.model import identify_overhead


def read(p):return json.loads(p.read_text())


def aggregate_delta(a):
    before='\n'.join(x for x in a.get('aggregation_before',{}).values() if isinstance(x,str))
    after='\n'.join(x for x in a.get('aggregation_after',{}).values() if isinstance(x,str))
    def counts(text):return {int(k):int(v) for k,v in re.findall(r'AMSDU pack count of (\d+) MSDU in TXD:\s*(\d+)',text)}
    x,y=counts(before),counts(after);d={k:y[k]-x[k] for k in x if k in y}
    if not d or any(v<0 for v in d.values()):return None
    n=sum(d.values())
    return {'amsdu_pack_counts':d,'mean_MSDU_per_TXD':sum(k*v for k,v in d.items())/n if n else None,'note':'driver cumulative TXD grouping counts; not full PPDU airtime or AP aggregation'}


def extract(folder,trial):
    sender=trial['sender'];other='5' if sender=='4' else '4';name=trial['name']
    a=read(folder/(sender+'_'+name+'.json'));b=read(folder/(other+'_'+name+'.json'))
    rows=a['rows'];traffic=a['traffic']
    if traffic:
        rows=[r for r in rows if traffic['start_mono_s']+3<=r['mono_s']<=traffic['end_mono_s']-3]
    elif len(rows)>8:rows=rows[3:-3]
    if len(rows)<2:rows=[a['rows'][0],a['rows'][-1]]
    x,y=rows[0]['counters'],rows[-1]['counters'];keys=['active_s','busy_s','tx_s','rx_s','bytes','packets','retries','station_tx_us','station_rx_us']
    d={k:y[k]-x[k] for k in keys if k in x and k in y}
    elapsed=d['active_s']
    if elapsed<=0 or any(v<0 for v in d.values()):raise ValueError('stale/reset counters')
    rxrows=b['rows']
    if traffic:
        # Wall alignment only for multi-second radio summaries, not E2E latency.
        selected=[r for r in rxrows if traffic['start_wall_ns']+3e9<=r['wall_ns']<=traffic['end_wall_ns']-3e9]
        if len(selected)>=2:rxrows=selected
    tx=statistics.median(r['counters']['tx_bps'] for r in rows)
    rx=statistics.median(r['counters']['rx_bps'] for r in rxrows)
    return {'name':name,'mode':trial['mode'],'requested_bps':trial['requested_bps'],'receiver_bps':(trial['receiver_Mbps'] or 0)*1e6,
            'elapsed_s':elapsed,'busy_fraction':d['busy_s']/elapsed,'tx_fraction':d['tx_s']/elapsed,'station_byte_Bps':d['bytes']/elapsed,
            'retry_per_packet':d['retries']/max(1,d['packets']),'tx_Bps':tx/8,'rx_Bps':rx/8,'delta':d,'sender_samples':len(rows),
            'aggregation_sender':aggregate_delta(a),'aggregation_receiver':aggregate_delta(b),
            'udp_errors':{h:{k:raw['rows'][-1].get('udp',{}).get(k,0)-raw['rows'][0].get('udp',{}).get(k,0) for k in ['RcvbufErrors','SndbufErrors']} for h,raw in [(sender,a),(other,b)]},
            'scope':'steady middle window; receiver PHY is receiver station RX; wall alignment is not a latency clock'}


def interpolate(nodes,x,key):
    if x<nodes[0]['station_byte_Bps'] or x>nodes[-1]['station_byte_Bps']:raise ValueError('outside fitted own-load range')
    for lo,hi in zip(nodes,nodes[1:]):
        if lo['station_byte_Bps']<=x<=hi['station_byte_Bps']:
            t=(x-lo['station_byte_Bps'])/(hi['station_byte_Bps']-lo['station_byte_Bps'])
            return lo[key]+t*(hi[key]-lo[key])
    return nodes[-1][key]


def estimate(profile,d):
    retry=d['retry_per_packet'];u=1400;packet=1428;O=profile['O_saturated_s']
    theta=(1+retry)/u*(2*O+packet/d['tx_Bps']+packet/d['rx_Bps'])
    rate=d['station_byte_Bps'];relay=(1+retry)*rate/u*(O+packet/d['rx_Bps'])
    physical_beta=d['busy_fraction']-relay
    result={'constant_O_beta_unclipped':physical_beta,'constant_O_prediction_bps':8*(1-physical_beta)/theta}
    if rate>0:
        try:
            o=interpolate(profile['relay_nodes'],rate,'effective_relay_O_s')
            # Sender retries apply to the uplink; they do not create a second
            # AP downlink for each failed uplink attempt.
            expected=rate/u*(o+packet/d['rx_Bps'])
            beta=d['busy_fraction']-profile['idle_busy_fraction']-expected
            split=profile['O_saturated_split_retry_s']
            candidate_theta=((1+retry)*(split+packet/d['tx_Bps'])+split+packet/d['rx_Bps'])/u
            result.update(empirical_beta_unclipped=beta,empirical_prediction_bps=8*(1-beta)/candidate_theta,effective_relay_O_s=o)
        except ValueError as e:result['empirical_error']=str(e)
    return result


def estimate_burst(profile,d):
    down=profile['relay_nodes'][-1]['effective_relay_O_s'];inputs=profile['inputs'];nu=inputs['retries']
    up=(1400/inputs['capacity']-(1+nu)*1428/inputs['tx_rate']-1428/inputs['rx_rate']-down)/(1+nu)
    if up<0 or down<0:raise ValueError('inconsistent effective hop costs')
    relay=d['station_byte_Bps']/1400*(down+1428/d['rx_Bps'])
    beta=d['busy_fraction']-profile['idle_busy_fraction']-relay
    theta=((1+d['retry_per_packet'])*(up+1428/d['tx_Bps'])+down+1428/d['rx_Bps'])/1400
    return {'burst_beta_unclipped':beta,'burst_prediction_bps':8*(1-beta)/theta,'burst_effective_up_O_s':up,'burst_effective_down_O_s':down}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['fit','validate']);p.add_argument('--run',required=True);p.add_argument('--stage',default='validation');p.add_argument('--profile',default='frozen_radio_profile_v2.json');a=p.parse_args()
    base=ROOT/'runs'/a.run;profilefile=base/a.profile
    if a.mode=='fit':
        if profilefile.exists():raise ValueError('preserve frozen profile')
        calfolder=base/'calibration';trainfolder=base/'training'
        cal=read(calfolder/'summary.json');train=read(trainfolder/'summary.json')
        calrows=[extract(calfolder,t) for t in cal['trials']];trainrows=[extract(trainfolder,t) for t in train['trials']]
        inputs={'capacity':cal['C0_receiver_median_bps']/8,'tx_rate':statistics.median(d['tx_Bps'] for d in calrows),'rx_rate':statistics.median(d['rx_Bps'] for d in calrows),'retries':statistics.median(d['retry_per_packet'] for d in calrows),'unit':1400,'header':0}
        O=identify_overhead(**inputs);idle=statistics.median(d['busy_fraction'] for d in trainrows if d['mode']=='idle')
        retry=inputs['retries'];splitO=(1400/inputs['capacity']-(1+retry)*1428/inputs['tx_rate']-1428/inputs['rx_rate'])/(2+retry)
        if splitO<0:raise ValueError('inconsistent split-retry saturated calibration')
        nodes=[]
        for d in trainrows:
            if d['mode']!='relay':continue
            rate=d['station_byte_Bps'];effective=(d['busy_fraction']-idle)*1400/rate-1428/d['rx_Bps']
            if effective<0:raise ValueError('inconsistent negative effective relay overhead')
            nodes.append({**d,'effective_relay_O_s':effective})
        # Saturated training supplies the upper endpoint; it is not held out.
        d={k:statistics.median(r[k] for r in calrows) for k in ['busy_fraction','station_byte_Bps','retry_per_packet','rx_Bps']}
        d['effective_relay_O_s']=(d['busy_fraction']-idle)*1400/d['station_byte_Bps']-1428/d['rx_Bps']
        if d['effective_relay_O_s']<0:raise ValueError('inconsistent saturated relay calibration')
        nodes.append(d);nodes.sort(key=lambda d:d['station_byte_Bps'])
        profile={'scope':'candidate UDP1400/iperf pacing1000us, main4->5, AX1500 channel149/80MHz, mt7921 Ubuntu6.8.0-138; not normal adaptive approval',
                 'version':2,'revision_basis':'training-only correction: uplink retry ratio is not applied to AP downlink; v1 had a negative saturated relay overhead and is rejected',
                 'C0_bps':cal['C0_receiver_median_bps'],'inputs':inputs,'O_saturated_s':O,'O_saturated_split_retry_s':splitO,'idle_busy_fraction':idle,'relay_nodes':nodes,'training_rows':trainrows,'calibration_rows':calrows,
                 'criteria_declared_before_validation':{'selfload_abs_beta_max':.05,'capacity_relative_error_max':.2,'all_trials_required':True,'no_raw_beta_clipping':True},
                 'production_adaptive_qualified':False,'training_files_sha256':{str(f.relative_to(base)):hashlib.sha256(f.read_bytes()).hexdigest() for folder in [calfolder,trainfolder] for f in folder.glob('*.json')}}
        profilefile.write_text(json.dumps(profile,indent=2));print(json.dumps({'profile_sha256':hashlib.sha256(profilefile.read_bytes()).hexdigest(),'O_sat_us':O*1e6,'relay_nodes':[{'station_Mbps':d['station_byte_Bps']*8/1e6,'busy':d['busy_fraction'],'O_relay_us':d['effective_relay_O_s']*1e6} for d in nodes]}))
    else:
        profile=read(profilefile);folder=base/a.stage;rows=[]
        for trial in read(folder/'summary.json')['trials']:
            d=extract(folder,trial)
            if d['mode']=='relay':
                d.update(estimate(profile,d));d.update(estimate_burst(profile,d));d['selfload_candidate_pass']=abs(d.get('empirical_beta_unclipped',math.inf))<=.05
                d['burst_candidate_pass']=abs(d['burst_beta_unclipped'])<=.05
            rows.append(d)
        result={'frozen_profile_sha256':hashlib.sha256(profilefile.read_bytes()).hexdigest(),'rows':rows,'all_selfload_pass':all(r.get('selfload_candidate_pass',True) for r in rows),'all_burst_candidate_pass':all(r.get('burst_candidate_pass',True) for r in rows),'normal_adaptive_qualified':False}
        (folder/'analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps({'all_selfload_pass':result['all_selfload_pass'],'all_burst_candidate_pass':result['all_burst_candidate_pass'],'rows':[{'name':d['name'],'busy':d['busy_fraction'],'tx':d['tx_fraction'],'constant_beta':d.get('constant_O_beta_unclipped'),'empirical_beta':d.get('empirical_beta_unclipped'),'burst_beta':d.get('burst_beta_unclipped'),'error':d.get('empirical_error')} for d in rows]}))


if __name__=='__main__':main()
