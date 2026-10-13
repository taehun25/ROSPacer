"""Evaluate fixed calibration on B2/C2; never fit to competing runs."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from deploy import ROOT
from w1_radio_evidence import steady
from w1_counter_analysis import estimate,estimate_burst,extract
sys.path.insert(0,str(ROOT))
from rospacer.model import identify_overhead


def read(p):return json.loads(p.read_text())


def delta(folder,name):
    d=steady(folder,name,4)
    return {'busy_fraction':d['busy_s']/d['active_s'],'tx_fraction':d['tx_s']/d['active_s'],'station_byte_Bps':d['bytes']/d['active_s'],
            'retry_per_packet':d['retries']/max(1,d['packets']),'tx_Bps':d['tx_Bps'],'rx_Bps':d['rx_Bps'],'raw_delta':d}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['fit-sr2','validate']);p.add_argument('--run',required=True);p.add_argument('--condition',choices=['b2','c2','b2_v2','b2_scheduled','b2_scheduled_v2','b2_scheduled_v3','c2_scheduled']);a=p.parse_args()
    base=ROOT/'runs'/a.run
    if a.mode=='fit-sr2':
        profile=read(base/'frozen_radio_profile_v2.json');folder=base/'c2';cal=[read(folder/(n+'_summary.json')) for n in ['quiet1','quiet2','quiet3']]
        ds=[delta(folder,t['name']) for t in cal];capacity=statistics.median(t['receiver_bps'] for t in cal)
        inputs={'capacity':capacity/8,'tx_rate':statistics.median(d['tx_Bps'] for d in ds),'rx_rate':statistics.median(d['rx_Bps'] for d in ds),'retries':statistics.median(d['retry_per_packet'] for d in ds),'unit':1400,'header':0}
        split=(1400/inputs['capacity']-(1+inputs['retries'])*1428/inputs['tx_rate']-1428/inputs['rx_rate'])/(2+inputs['retries'])
        if split<0:raise ValueError('inconsistent saturated PHY inputs on SR2')
        profile.update(C0_bps=capacity,inputs=inputs,O_saturated_s=identify_overhead(**inputs),O_saturated_split_retry_s=split,
                       scope='SR2 capacity recalibrated using quiet1..3 only; AX1500 relay curve transferred unchanged; transfer is held out, not assumed valid',
                       parent_profile_sha256=hashlib.sha256((base/'frozen_radio_profile_v2.json').read_bytes()).hexdigest(),sr2_calibration=[{'trial':t['name'],'capacity_bps':t['receiver_bps'],'delta':d} for t,d in zip(cal,ds)])
        dest=folder/'frozen_radio_profile_v2_sr2.json'
        if dest.exists():raise ValueError('preserve frozen SR2 profile')
        dest.write_text(json.dumps(profile,indent=2));other=ROOT/'runs'/(a.run+'_sr2');other.mkdir(parents=True,exist_ok=True)
        (other/'frozen_radio_profile_v2.json').write_bytes(dest.read_bytes())
        print(json.dumps({'C0_SR2_Mbps':capacity/1e6,'profile_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}))
    else:
        folder=base/a.condition;profilepath=base/'c2/frozen_radio_profile_v2_sr2.json' if a.condition.startswith('c2') else base/'frozen_radio_profile_v2.json';profile=read(profilepath)
        trials=read(folder/'summary.json')['trials'];rows=[]
        for t in trials:
            d=extract(folder,t) if '_scheduled' in a.condition else delta(folder,t['name']);result={**estimate(profile,d),**estimate_burst(profile,d)};actual=t.get('receiver_bps',t.get('receiver_Mbps',0)*1e6)
            row={'name':t['name'],'actual_bps':actual,'delta':d,**result,'protocol_valid':t.get('protocol_valid',True),'intentional_competition':t.get('intentional_competition',t['name'].startswith('B2') or t['name'].startswith('C2'))}
            for key in ['constant_O','empirical','burst']:
                pred=row.get(key+'_prediction_bps');row[key+'_error_fraction']=abs(pred-actual)/actual if pred is not None else None
            row['candidate_pass']=row['protocol_valid'] and row.get('empirical_error_fraction') is not None and row['empirical_error_fraction']<=.2
            rows.append(row)
        competing=[r for r in rows if r['intentional_competition']]
        output={'profile_sha256':hashlib.sha256(profilepath.read_bytes()).hexdigest(),'rows':rows,'all_competition_pass':len(competing)==3 and all(r['candidate_pass'] for r in competing),'all_burst_competition_pass':len(competing)==3 and all(r['protocol_valid'] and r['burst_error_fraction']<=.2 for r in competing),
                'normal_adaptive_qualified':False,'reason':'capacity mean-error probe; DDS burst generalisation and continuous input contract are separate gates'}
        (folder/'analysis.json').write_text(json.dumps(output,indent=2));print(json.dumps({'condition':a.condition,'all_competition_pass':output['all_competition_pass'],'all_burst_competition_pass':output['all_burst_competition_pass'],'rows':[{'name':r['name'],'actual_Mbps':r['actual_bps']/1e6,'beta':r.get('empirical_beta_unclipped'),'pred_Mbps':r.get('empirical_prediction_bps',0)/1e6,'error_percent':100*r['empirical_error_fraction'] if r['empirical_error_fraction'] is not None else None,'burst_error_percent':100*r['burst_error_fraction'],'error':r.get('empirical_error')} for r in rows]}))


if __name__=='__main__':main()
