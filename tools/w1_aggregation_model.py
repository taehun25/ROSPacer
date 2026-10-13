"""Training-only AP response/aggregation calibration and held-out checks."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from deploy import ROOT


U32={'rx_ba_cnt','rx_ampdu_cnt','rx_mpdu_cnt','rx_ampdu_bytes_cnt','tx_ampdu_cnt'}


def read(p):return json.loads(p.read_text())


def features(a4,a5,lo=None,hi=None,coverage_scale=1.05):
    rows=a4['rows'];traffic=a4.get('traffic',{})
    if lo is None and traffic:lo,hi=traffic['start_mono_s']+3,traffic['end_mono_s']-3
    if lo is not None:rows=[r for r in rows if lo<=r['mono_s']<=hi]
    elif len(rows)>10:rows=rows[3:-3]
    if len(rows)<2:raise ValueError('insufficient source samples')
    recv=[r for r in a5['rows'] if rows[0]['wall_ns']<=r['wall_ns']<=rows[-1]['wall_ns']]
    if len(recv)<2:raise ValueError('insufficient receiver samples')
    x,y=rows[0]['counters'],rows[-1]['counters'];d={k:y[k]-x[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']};elapsed=d['active_s']
    def diff(records,key):
        first,last=records[0]['etstats'][key],records[-1]['etstats'][key]
        result=last-first
        if result<0 and key in U32:result+=2**32
        if result<0:raise ValueError('unqualified counter reset')
        return result
    er=recv[-1]['counters']['active_s']-recv[0]['counters']['active_s'];scale=elapsed/er
    rxbytes=diff(recv,'rx_bytes')*scale;rxpackets=diff(recv,'rx_packets')*scale;mpdu=diff(recv,'rx_mpdu_cnt')*scale;ampdu=diff(recv,'rx_ampdu_cnt')*scale
    rx_duration=(recv[-1]['counters']['station_rx_us']-recv[0]['counters']['station_rx_us'])/1e6*scale
    ampdu_bytes=diff(recv,'rx_ampdu_bytes_cnt')*scale
    ratio=ampdu_bytes/rxbytes if rxbytes else None
    if ratio is not None and ratio>coverage_scale*1.1:raise ValueError('AMPDU byte accounting outside AP-specificcalibration')
    coverage=min(1,ampdu_bytes/(coverage_scale*rxbytes)) if rxbytes else 0
    # RX AMPDU count misses standalone MPDUs. Byte coverage supplies a
    # calibrated approximation, retaining the raw ratio and its uncertainty.
    ppdu=ampdu+mpdu*(1-coverage)
    down=statistics.median(r['counters']['rx_bps'] for r in recv)/8
    return {'active_s':elapsed,'busy_s':d['busy_s'],'tx_s':d['tx_s'],'bytes':d['bytes'],'packets':d['packets'],'retry_per_packet':d['retries']/max(1,d['packets']),
            'tx_Bps':statistics.median(r['counters']['tx_bps'] for r in rows)/8,'rx_Bps':down,'BA_source':diff(rows,'rx_ba_cnt'),'AMPDU_receiver':ampdu,'MPDU_receiver':mpdu,'rx_bytes_receiver':rxbytes,'rx_packets_receiver':rxpackets,
            'data_time_proxy_s':(rxbytes-14*rxpackets+50*mpdu)/down,'rx_duration_s':rx_duration,'rx_duration_stale':rxpackets>100 and rx_duration<=0,'AMPDU_bytes_ratio_raw':ratio,'PPDU_receiver_estimated':ppdu,'RX_MSDU_per_AMPDU':rxpackets/ampdu if ampdu else None}


def predict(profile,f):
    own=profile['BA_busy_s']*f['BA_source']+profile['RX_data_scale']*f['data_time_proxy_s']+profile['RX_AMPDU_busy_s']*f['PPDU_receiver_estimated']
    beta=(f['busy_s']-profile['idle_busy_fraction']*f['active_s']-own)/f['active_s']
    return {'own_visible_busy_s':own,'beta_unclipped':beta,'self_pass':abs(beta)<=.05}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['fit','dds','burst','c2','b2']);p.add_argument('--run',required=True);p.add_argument('--dds-label',default='dds_radio_v2');p.add_argument('--condition-label');p.add_argument('--coverage-profile');a=p.parse_args()
    base=ROOT/'runs'/a.run;file=base/'frozen_aggregation_coverage_profile.json'
    if a.mode=='fit':
        if file.exists():raise ValueError('preserve frozen profile')
        ackfolder=base/'ack_reference';trainfolder=base/'aggregation_training'
        ack=[];idle=[]
        for t in read(ackfolder/'summary.json')['trials']:
            f=features(read(ackfolder/('4_'+t['name']+'.json')),read(ackfolder/('5_'+t['name']+'.json')))
            (ack if t['mode']=='ap_only' else idle).append(f)
        baseline=statistics.median(f['busy_s']/f['active_s'] for f in idle)
        h=statistics.median((f['busy_s']-baseline*f['active_s'])/f['BA_source'] for f in ack)
        data=[]
        for t in read(trainfolder/'summary.json')['trials']:
            if t['mode']!='relay':continue
            f=features(read(trainfolder/('4_'+t['name']+'.json')),read(trainfolder/('5_'+t['name']+'.json')));data.append({'name':t['name'],'features':f})
        xs=[(r['features']['data_time_proxy_s'],r['features']['PPDU_receiver_estimated'],r['features']['busy_s']-baseline*r['features']['active_s']-h*r['features']['BA_source']) for r in data]
        aa=sum(x*x for x,y,z in xs);bb=sum(y*y for x,y,z in xs);ab=sum(x*y for x,y,z in xs);az=sum(x*z for x,y,z in xs);bz=sum(y*z for x,y,z in xs);det=aa*bb-ab*ab
        if det<=1e-8*aa*bb:raise ValueError('unidentifiable calibration')
        c1=(az*bb-bz*ab)/det;c2=(bz*aa-az*ab)/det
        if not (.5<=c1<=2 and 0<=c2<=.001 and 0<h<.001):raise ValueError('nonphysical effective calibration '+str((h,c1,c2)))
        profile={'BA_busy_s':h,'RX_data_scale':c1,'RX_AMPDU_busy_s':c2,'idle_busy_fraction':baseline,'ack_rows':ack,'training_rows':data,'normal_adaptive_qualified':False,'receiver_input':'receiverRXbytes,MPDU,AMPDU andAMPDUbytes; durationstaleness preserved','AMPDU_byte_coverage_scale':1.05,'coverage_assumption':'effective5percentMAC-byte/duplicate allowance; raw ratios retained; estimatedstandalonePPDUs require independentvalidation',
                 'scope':'operational busy contribution calibration; PPDU coefficient is effective, not a claim of intrinsic PHY preamble time. RX is receiver native API, BA is sender native API.',
                 'criteria':{'self_abs_beta_max':.05,'capacity_error_max':.2},'training_sha256':{str(f.relative_to(base)):hashlib.sha256(f.read_bytes()).hexdigest() for folder in [ackfolder,trainfolder] for f in folder.glob('*.json')}}
        profile['training_residuals']=[{'name':r['name'],**predict(profile,r['features'])} for r in data];file.write_text(json.dumps(profile,indent=2));print(json.dumps({'BA_us':h*1e6,'RX_scale':c1,'AMPDU_effective_us':c2*1e6,'training_residuals':profile['training_residuals']}))
    else:
        profile=read(file);rows=[]
        if a.mode=='dds':
            folder=base/a.dds_label
            for dir in sorted(folder.iterdir()):
                if not dir.is_dir() or not (dir/'summary.json').exists():continue
                pub=read(dir/'4/pub.json');f=features(read(dir/'4/radio.json'),read(dir/'5/radio.json'),pub['measurement_started_ns']/1e9+2,pub['measurement_ended_ns']/1e9-2);rows.append({'name':dir.name,'features':f,**predict(profile,f)})
        else:
            folder=base/(a.condition_label or ('burst_validation' if a.mode=='burst' else 'b2_aggregation_confirmation' if a.mode=='b2' else 'c2_scheduled'))
            coverage_scale=1.05
            if a.mode=='c2' and a.coverage_profile:
                calibration=read(base/a.coverage_profile);coverage_scale=calibration['coverage_scale']
                if calibration['source']!='quiet only; competitor data not used':raise ValueError('unqualified byte coverage source')
                (folder/'aggregation_byte_calibration.json').write_text(json.dumps({**calibration,'frozen_parent':a.coverage_profile,'parent_sha256':hashlib.sha256((base/a.coverage_profile).read_bytes()).hexdigest()},indent=2))
            elif a.mode=='c2':
                q=read(folder/'5_quiet.json')['rows'];first,last=q[0]['etstats'],q[-1]['etstats']
                ratio=((last['rx_ampdu_bytes_cnt']-first['rx_ampdu_bytes_cnt'])%(2**32))/(last['rx_bytes']-first['rx_bytes'])
                coverage_scale=ratio*1.05
                (folder/'aggregation_byte_calibration.json').write_text(json.dumps({'source':'quiet only; competitor data not used','observed_ratio':ratio,'coverage_scale':coverage_scale,'normal_adaptive_qualified':False},indent=2))
            for t in read(folder/'summary.json')['trials']:
                if t.get('mode')!='relay':continue
                f=features(read(folder/('4_'+t['name']+'.json')),read(folder/('5_'+t['name']+'.json')),coverage_scale=coverage_scale);row={'name':t['name'],'features':f,**predict(profile,f)}
                if a.mode in ('c2','b2'):
                    bulk=read(base/('c2/frozen_radio_profile_v2_sr2.json' if a.mode=='c2' else 'frozen_radio_profile_v2.json'));O=bulk['O_saturated_split_retry_s'];nu=f['retry_per_packet'];theta=((1+nu)*(O+1428/f['tx_Bps'])+O+1428/f['rx_Bps'])/1400
                    row['prediction_bps']=8*(1-row['beta_unclipped'])/theta;row['actual_bps']=t['receiver_Mbps']*1e6;row['error_fraction']=abs(row['prediction_bps']-row['actual_bps'])/row['actual_bps']
                rows.append(row)
        output={'rows':rows,'all_self_pass':all(r['self_pass'] for r in rows),'profile_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'normal_adaptive_qualified':False}
        (folder/'aggregation_analysis.json').write_text(json.dumps(output,indent=2));print(json.dumps({'all_self_pass':output['all_self_pass'],'rows':[{'name':r['name'],'beta':r['beta_unclipped'],'pass':r['self_pass'],'capacity_error_percent':100*r['error_fraction'] if 'error_fraction' in r else None} for r in rows]}))


if __name__=='__main__':main()
