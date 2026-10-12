"""Retain unmodified counter evidence; do not repair negative residuals by clipping."""
import argparse
import json
from pathlib import Path
import statistics
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.model import identify_overhead,adaptive_rate


def steady(folder,name,margin=3):
    c=json.loads((folder/(name+'_client.json')).read_text())
    rows=[json.loads(s) for s in (folder/('4_'+name+'_telemetry.jsonl')).read_text().splitlines()]
    rows=[r for r in rows if c['start_mono']+margin<r['monotonic_s']<c['end_mono']-margin]
    w=[r['wireless'] for r in rows]
    d={k:w[-1][k]-w[0][k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}
    d['elapsed_s']=d['active_s'];d['tx_Bps']=statistics.median(r['tx_Bps'] for r in w)
    # Receiver station's RX PHY, not sender station's RX PHY.
    receive=[json.loads(s)['wireless'] for s in (folder/('5_'+name+'_telemetry.jsonl')).read_text().splitlines()]
    d['rx_Bps']=statistics.median(r['rx_Bps'] for r in receive[20:-20])
    d['samples']=len(w)
    d['rx_rate_source']='receiver station dump RX PHY (campaign-median; not instantaneous downlink feedback)'
    d['sender_tx_duration_s']=None
    import re
    x=[re.search(r'tx duration:\s*(\d+) us',r['station_raw']) for r in [w[0],w[-1]]]
    if all(x):d['sender_tx_duration_s']=(int(x[1][1])-int(x[0][1]))/1e6
    return d


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);a=p.parse_args()
    base=ROOT/'runs'/a.run;cal=base/'calibration';C0=json.loads((cal/'summary.json').read_text())['C0_receiver_median_bps']/8
    samples=[steady(cal,n,4) for n in ['udp1','udp2','udp3']]
    inputs={'capacity':C0,'tx_rate':statistics.median(d['tx_Bps'] for d in samples),'rx_rate':statistics.median(d['rx_Bps'] for d in samples),'retries':statistics.median(d['retries']/d['packets'] for d in samples),'unit':1400,'header':0}
    o=identify_overhead(**inputs)
    cfg=dict(unit_bytes=1400,header_bytes=0,airtime_overhead_s=o,packet_factor=1428/1400,alpha=1.)
    result={'conditional_O_s':o,'inputs':inputs,'O_scope':'effective fit to UDP1400B saturated calibration; not intrinsic per-packet cost and not transplanted to DDS fragments','calibration_steady':samples,'selfload':[],'model_conditions':[],'survey_semantics_validated':False}
    for rho in [.2,.4,.6,.8]:
        n='rho'+str(rho);d=steady(base/'selfload',n)
        retry=d['retries']/max(1,d['packets']);relay=(1+retry)*d['bytes']/1400*(o+1428/d['rx_Bps'])
        r={'rho':rho,'delta':d,'busy_fraction':d['busy_s']/d['active_s'],'tx_fraction':d['tx_s']/d['active_s'],'relay_fraction':relay/d['active_s'],'proposal_beta_unclipped':(d['busy_s']-d['tx_s']-relay)/d['active_s'],'alternative_excludes_self_tx_beta_unclipped':(d['busy_s']-relay)/d['active_s']}
        try:r['strict_estimate']=adaptive_rate(cfg,d,True)
        except ValueError as e:r['strict_estimate_error']=str(e)
        result['selfload'].append(r)
    for label in ['b2','c2']:
        folder=base/label
        if not folder.exists():continue
        condition_cfg=dict(cfg)
        if label=='c2' and all((folder/(n+'_summary.json')).exists() for n in ['quiet1','quiet2','quiet3']):
            quiet=[steady(folder,n,4) for n in ['quiet1','quiet2','quiet3']]
            rates=[json.loads((folder/(n+'_summary.json')).read_text())['receiver_bps']/8 for n in ['quiet1','quiet2','quiet3']]
            fit=dict(capacity=statistics.median(rates),tx_rate=statistics.median(d['tx_Bps'] for d in quiet),rx_rate=statistics.median(d['rx_Bps'] for d in quiet),retries=statistics.median(d['retries']/d['packets'] for d in quiet),unit=1400,header=0)
            try:condition_cfg['airtime_overhead_s']=identify_overhead(**fit);result['c2_calibration']={'inputs':fit,'conditional_O_s':condition_cfg['airtime_overhead_s']}
            except ValueError as e:result['c2_calibration']={'inputs':fit,'error':str(e)}
        for f in sorted(folder.glob('*_summary.json')):
            n=f.name[:-13];trial=json.loads(f.read_text());d=steady(folder,n)
            row={'condition':label,'trial':n,'measured_receiver_bps':trial['receiver_bps'],'delta':d,'qualified_prediction_bps':None,'qualified_error_percent':None}
            row['conditional_O_s']=condition_cfg['airtime_overhead_s']
            try:row['strict_model_candidate']=adaptive_rate(condition_cfg,d,True)
            except ValueError as e:row['strict_model_error']=str(e)
            # Diagnostic counterfactual, explicitly unqualified: beta subtraction
            # treating raw busy as excluding self TX. No mutation of raw data.
            oo=condition_cfg['airtime_overhead_s'];retry=d['retries']/max(1,d['packets']);relay=(1+retry)*d['bytes']/1400*(oo+1428/d['rx_Bps']);beta=(d['busy_s']-relay)/d['active_s'];theta=(1+retry)/1400*(2*oo+1428/d['tx_Bps']+1428/d['rx_Bps']);candidate=(1-max(0,min(1,beta)))/theta*8
            row.update(alternative_unqualified_beta_unclipped=beta,alternative_unqualified_prediction_bps=candidate,alternative_unqualified_error_percent=100*abs(candidate-trial['receiver_bps'])/trial['receiver_bps'],reason='self-load failed survey semantics; no qualified prediction or20percent acceptance')
            result['model_conditions'].append(row)
    (base/'radio_evidence.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'O_us':o*1e6,'selfload':[{'rho':r['rho'],'beta_raw':r['proposal_beta_unclipped'],'alternative_beta_raw':r['alternative_excludes_self_tx_beta_unclipped']} for r in result['selfload']],'conditions':result['model_conditions']}))


if __name__=='__main__':main()
