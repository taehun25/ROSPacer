"""Frozen sender-only qualification; receiver data is offline reference only."""
import csv,json,math,statistics
from collections import Counter
from pathlib import Path
from deploy import ROOT

BASE=ROOT/'runs/w1_20261013_sender_validation'

def quantile(values,p):
    v=sorted(values)
    return v[min(len(v)-1,math.ceil(p*len(v))-1)] if v else None

def trial(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    client=json.loads((folder/'client.json').read_text())
    lifecycle=json.loads((folder/'lifecycle.json').read_text())
    server=json.loads((folder/'5/server.json').read_text())
    intervals=[s for x in server.get('intervals',[]) for s in x.get('streams',[]) if not s.get('omitted')]
    seconds=sum(s['seconds'] for s in intervals)
    goodput=8*sum(s['bytes'] for s in intervals)/seconds/1e6 if seconds else None
    radio=json.loads((folder/'5/reference_radio.json').read_text())
    udp={k:radio['rows'][-1]['udp'][k]-radio['rows'][0]['udp'][k] for k in ['InErrors','RcvbufErrors','SndbufErrors']}
    result={'tag':folder.name,'requested_Mbps':manifest['rate_requested_Mbps'],'monitor':manifest['monitor'],'client_rc':client['rc'],
            'receiver_goodput_Mbps':goodput,'receiver_udp_delta':udp,'receiver_counter_errors':radio['errors'],
            'lifecycle':lifecycle,'valid_transport':client['rc']==0 and seconds>0 and not any(udp.values()) and not radio['errors']}
    packets=sum(s.get('packets',0) for s in intervals);lost=sum(s.get('lost_packets',0) for s in intervals)
    result['receiver_udp_loss_percent']=100*lost/packets if packets else None
    if manifest['monitor']:
        rows=list(csv.DictReader((folder/'4/sender.csv').open()))
        steady=[r for r in rows if client['start_monotonic']+4<=float(r['monotonic_s'])<=client['end_monotonic']-2]
        estimated=[r for r in steady if r['status']=='estimated']
        fraction=len(estimated)/len(steady) if steady else 0
        betas=[float(r['beta']) for r in estimated]
        capacities=[(1-float(r['beta']))/float(r['theta'])*1400/float(r['mean_station_bytes'])*8/1e6 for r in estimated]
        coverage=[float(r['body_coverage']) for r in steady if r['body_coverage']]
        result.update(steady_windows=len(steady),estimated_windows=len(estimated),success_fraction=fraction,
                      hold_reasons=dict(Counter(r['error'] for r in steady if r['status']=='hold')),
                      beta_median=statistics.median(betas) if betas else None,beta_abs_p95=quantile([abs(b) for b in betas],.95),
                      body_coverage_p05=quantile(coverage,.05),body_coverage_median=statistics.median(coverage) if coverage else None,
                      body_coverage_p95=quantile(coverage,.95),
                      capture_drops_max=max([int(r['capture_drops']) for r in steady if r['capture_drops']]+[0]),
                      raw_capacity_payload_Mbps_median=statistics.median(capacities) if capacities else None,
                      input_sufficiency_pass=result['valid_transport'] and fraction>=.95,
                      stability_pass=lifecycle['healthy_without_reconnect'])
        if folder.name.startswith('self'):
            result['self_beta_pass']=result['input_sufficiency_pass'] and result['beta_abs_p95'] is not None and result['beta_abs_p95']<=.05
        if manifest['rate_requested_Mbps']==0 and goodput and capacities:
            result['capacity_relative_error']=abs(statistics.median(capacities)-goodput)/goodput
            result['capacity_pass']=result['input_sufficiency_pass'] and result['capacity_relative_error']<=.2
    return result

def main():
    excluded={'baseline_nomonitor','self02_r1'}
    results=[];errors={}
    for f in sorted(BASE.iterdir()):
        if not f.is_dir() or not (f/'manifest.json').exists() or f.name in excluded:continue
        try:
            r=trial(f);(f/'qualification.json').write_text(json.dumps(r,indent=2));results.append(r)
        except Exception as e:errors[f.name]=str(e)
    report={'protocol':json.loads((BASE/'protocol.json').read_text()),'results':results,'analysis_errors':errors,
            'excluded_pilots':{'baseline_nomonitor':'receiver UDP receive-buffer overflow; not RF qualification','self02_r1':'failed transport; original archive and lifecycle check occurred before observer completion; final_4/5 preserves complete data'},
            'profile_validated':False,'HTB_applied':False,'receiver_feedback_used':False,
            'scope':'Input sufficiency and stability; no full adaptive-vs-static performance claim.'}
    (BASE/'qualification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps([{k:r.get(k) for k in ['tag','client_rc','receiver_goodput_Mbps','success_fraction','body_coverage_median','beta_abs_p95','input_sufficiency_pass','stability_pass','capacity_relative_error']} for r in results],indent=2))
if __name__=='__main__':main()
