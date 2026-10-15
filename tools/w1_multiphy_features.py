"""Disjoint sender-only training features, with throughput offline reference."""
import argparse,bisect,csv,json,statistics,sys
from pathlib import Path
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.sender_radio import pcap_frames,decode,summarize,window_uplink
BASE=ROOT/'runs/w1_20261014_sender_multiphy'

def extract(folder):
    if (folder/'client.json').exists():
        client=json.loads((folder/'client.json').read_text());manifest=json.loads((folder/'manifest.json').read_text())
    else:
        pub=json.loads((folder/'4/pub.json').read_text());summary=json.loads((folder/'summary.json').read_text());client={'rc':0 if pub['succeeded']==pub['requested'] else 1,'start_monotonic':pub['measurement_started_ns']/1e9,'end_monotonic':pub['measurement_ended_ns']/1e9}
        manifest={'rate_requested_Mbps':None,'DDS':summary,'source_sha256':summary['source_sha256']}
    profile=json.loads((BASE/'training_diagnostic.json').read_text())
    if client['rc']!=0:raise ValueError('failed training transport')
    samples=[json.loads(s) for s in (folder/'4/source_samples.jsonl').read_text().splitlines()]
    frames=[]
    for t,p,n in pcap_frames(folder/'4/sender.pcap'):
        try:parsed=decode(p,n,allow_bad_fcs=True)
        except ValueError as e:parsed={'parse_error':str(e)}
        frames.append((t,parsed,n))
    times=[x[0] for x in frames]
    trace=list(csv.DictReader((folder/'4/sender.csv').open()));reference=json.loads((folder/'5/reference_radio.json').read_text())['rows']
    windows=[];start=client['start_monotonic']+4;end=client['end_monotonic']-2
    while start+3<=end:
        rows=[x for x in samples if start<=x['monotonic_s']<=start+3]
        if len(rows)<8:raise ValueError('missing source sample window')
        old,new=rows[0]['sample'],rows[-1]['sample'];wall0=old['observed_wall_ns']/1e9;wall1=new['observed_wall_ns']/1e9
        visible=summarize(frames[bisect.bisect_left(times,wall0):bisect.bisect_right(times,wall1)],profile['AP'],profile['source_MAC'],profile['receiver_MAC'],profile['frequency_MHz'],True)
        d={k:new[k]-old[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}
        if d['active_s']<=0 or d['packets']<=0:raise ValueError('missing counter delta')
        coverage=visible['relay_unique_body_bytes']/d['bytes']
        window={'start_monotonic':rows[0]['monotonic_s'],'end_monotonic':rows[-1]['monotonic_s'],'delta':d,'visible':visible,'body_coverage':coverage,'up_Bps':window_uplink([x['sample'] for x in rows]),'down_Bps':visible['relay_rate_Bps'],
                'old':old,'new':new,'geometry_mean_station_bytes':d['bytes']/d['packets']}
        trace_window=[x for x in trace if rows[0]['monotonic_s']<=float(x['monotonic_s'])<=rows[-1]['monotonic_s']]
        window['capture_drops_max']=max([int(x['capture_drops']) for x in trace_window if x['capture_drops']]+[0])
        r0=min(reference,key=lambda x:abs(x['wall_ns']/1e9-wall0));r1=min(reference,key=lambda x:abs(x['wall_ns']/1e9-wall1))
        rx=r1['counters']['rx_bytes']-r0['counters']['rx_bytes'];expected_rx=d['bytes']-20*d['packets']
        window['offline_receiver_conservation_ratio']=rx/expected_rx if expected_rx>0 else None
        window['offline_pair_window_skew_s']=max(abs(r0['wall_ns']/1e9-wall0),abs(r1['wall_ns']/1e9-wall1))
        window['usable_features']=.8<=coverage<=1.1 and not visible['unknown_rate_body_bytes'] and visible['counts'].get('peer_ba',0)>0 and window['capture_drops_max']==0
        windows.append(window);start+=3
    server=json.loads((folder/'5/server.json').read_text()) if (folder/'5/server.json').exists() else {};streams=[x for t in server.get('intervals',[]) for x in t.get('streams',[])];duration=sum(x['seconds'] for x in streams)
    ref=json.loads((folder/'5/reference_radio.json').read_text());errors={k:ref['rows'][-1]['udp'][k]-ref['rows'][0]['udp'][k] for k in ['RcvbufErrors','SndbufErrors','InErrors']}
    idle=[x['sample'] for x in samples if x['monotonic_s']<client['start_monotonic']-.3]
    idle_rate=(idle[-1]['busy_s']-idle[0]['busy_s'])/(idle[-1]['active_s']-idle[0]['active_s']) if len(idle)>3 and idle[-1]['active_s']>idle[0]['active_s'] else None
    result={'tag':folder.name,'requested_Mbps':manifest['rate_requested_Mbps'],'windows':windows,'idle_busy_fraction':idle_rate,'receiver_payload_Bps':sum(x['bytes'] for x in streams)/duration if duration else None,'receiver_udp_errors':errors,'manifest':manifest,'scope':'disjoint windows; sender features only; receiver throughput is calibration/reference, never online feedback; PHYSICAL airtime not inferred'}
    (folder/'features.json').write_text(json.dumps(result,indent=2));return result
def main():
    p=argparse.ArgumentParser();p.add_argument('tags',nargs='+');a=p.parse_args()
    for tag in a.tags:
        if Path(tag).name!=tag:raise ValueError('single tag')
        r=extract(BASE/tag);print(json.dumps({'tag':tag,'usable_windows':sum(w['usable_features'] for w in r['windows']),'total_windows':len(r['windows']),'uplink_Mbps':[round(w['up_Bps']*8/1e6,1) for w in r['windows']],'downlink_Mbps':[round(w['down_Bps']*8/1e6,1) if w['down_Bps'] else None for w in r['windows']],'C0_Mbps':r['receiver_payload_Bps']*8/1e6 if r['receiver_payload_Bps'] else None,'UDP_errors':r['receiver_udp_errors']}),flush=True)
if __name__=='__main__':main()
