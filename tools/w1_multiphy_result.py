"""Held-out results; never changes fitted coefficients or calibration gates."""
import csv,hashlib,json,math,statistics
from collections import Counter
from deploy import ROOT
BASE=ROOT/'runs/w1_20261014_sender_multiphy'

def percentile(xs,p=.95):
    xs=sorted(xs)
    if not xs:return None
    i=(len(xs)-1)*p;a=int(i);b=math.ceil(i)
    return xs[a]+(xs[b]-xs[a])*(i-a)

def main():
    freeze=json.loads((BASE/'freeze_receipt.json').read_text())
    assert all(hashlib.sha256((BASE/k).read_bytes()).hexdigest()==v for k,v in freeze.items())
    protocol=json.loads((BASE/'protocol.json').read_text());results=[]
    for tag in protocol['validation_plan']:
        folder=BASE/tag
        if not folder.exists():continue
        dds=tag.startswith('dds_')
        if dds:
            pub=json.loads((folder/'4/pub.json').read_text());start=pub['measurement_started_ns']/1e9;end=pub['measurement_ended_ns']/1e9
        else:
            c=json.loads((folder/'client.json').read_text());start=c['start_monotonic'];end=c['end_monotonic']
        rows=list(csv.DictReader((folder/'4/sender.csv').open()))
        steady=[r for r in rows if start+4<=float(r['monotonic_s'])<=end-2]
        accepted=[r for r in steady if r['status']=='estimated']
        r={'tag':tag,'steady_windows':len(steady),'estimated_windows':len(accepted),'estimated_fraction':len(accepted)/len(steady) if steady else 0,
           'hold_reasons':dict(Counter(x['error'] for x in steady if x['status']=='hold')),
           'accepted_beta_abs_p95':percentile([abs(float(x['beta'])) for x in accepted]),
           'accepted_beta_median':statistics.median([float(x['beta']) for x in accepted]) if accepted else None,
           'input_fraction_pass':bool(steady) and len(accepted)/len(steady)>=.95,
           'receiver_feedback_used':False,'HTB_applied':False}
        if dds:
            r['DDS']=json.loads((folder/'summary.json').read_text())
        else:
            f=json.loads((folder/'features.json').read_text());r['received_payload_Mbps']=f['receiver_payload_Bps']*8/1e6
            r['receiver_udp_errors']=f['receiver_udp_errors']
            ratios=[w['offline_receiver_conservation_ratio'] for w in f['windows'] if w['offline_receiver_conservation_ratio'] is not None]
            r['offline_conservation_ratio_range']=[min(ratios),max(ratios)] if ratios else None
            r['offline_conservation_error_max']=max(abs(x-1) for x in ratios) if ratios else None
            r['offline_pair_window_skew_s_max']=max(w['offline_pair_window_skew_s'] for w in f['windows'])
            r['exit_lifecycle']=json.loads((folder/'lifecycle.json').read_text())
            server=json.loads((folder/'5/server.json').read_text());r['receiver_end_sum']=server.get('end',{}).get('sum',{})
            if tag.endswith('saturation'):
                # theta is per station-layer byte; compare UDP payload units and
                # remove alpha/headroom. Do not compare clipped/EMA HTB cap to C0.
                predictions=[(1-float(x['beta']))/float(x['theta'])*1400/float(x['mean_station_bytes'])*8/1e6 for x in accepted]
                r['conditional_uncapped_payload_prediction_Mbps']=statistics.median(predictions) if predictions else None
                r['conditional_capacity_relative_error']=abs(r['conditional_uncapped_payload_prediction_Mbps']/r['received_payload_Mbps']-1) if predictions else None
                r['capacity_validation_qualified']=r['input_fraction_pass'] and bool(predictions) and r['conditional_capacity_relative_error']<=.2
            background=BASE/(tag+'_background')
            if background.exists():
                inv=json.loads((background/'inventory.json').read_text());srv=json.loads((background/'10_server.json').read_text())
                r['background']={'kind':inv['kind'],'peer_ips':inv['ips'],'receiver_end_sum':srv.get('end',{}).get('sum',{}),
                                 'links':{h:n['link'] for h,n in inv['nodes'].items()},'restoration':json.loads((background/'restoration.json').read_text())}
        results.append(r)
    record={'results':results,'frozen_sha256':freeze,'thresholds':protocol['thresholds'],
            'input_sufficient':len(results)==len(protocol['validation_plan']) and all(x['input_fraction_pass'] for x in results),
            'approved':False,'latency_qualified':False,
            'scope':'prospective shadow observations; conditional errors on accepted windows cannot qualify a run failing95% availability; no held-out refit'}
    (BASE/'validation_results.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps([{k:r.get(k) for k in ['tag','estimated_windows','steady_windows','estimated_fraction','received_payload_Mbps','conditional_capacity_relative_error']} for r in results]),flush=True)
if __name__=='__main__':main()
