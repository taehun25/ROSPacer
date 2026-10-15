"""Sender-only calibration, with receiver captures used only as offline truth."""
import argparse
import json
from pathlib import Path
import statistics
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.sender_radio import pcap_frames,summarize,estimate


def trial(folder):
    rows=json.loads((folder/'4/radio.json').read_text())['rows']
    client=json.loads((folder/'client.json').read_text())
    # Select a central five-second counter window within the eight-second run.
    begin=client['start_wall']+1.5;end=client['end_wall']-1.5
    selected=[r for r in rows if begin<=r['wall_ns']/1e9<=end]
    if len(selected)<8:raise ValueError('insufficient central source counter window')
    first,last=selected[0],selected[-1];start=first['wall_ns']/1e9;stop=last['wall_ns']/1e9
    kwargs=dict(ap='b0:38:6c:7d:f5:74',source='3c:0a:f3:02:d9:3b',receiver='3c:0a:f3:02:e4:c7',exclusive_receiver=True)
    source=summarize((r for r in pcap_frames(folder/'4/air.pcap') if start<=r[0]<=stop),**kwargs)
    receiver=summarize((r for r in pcap_frames(folder/'5/air.pcap') if start<=r[0]<=stop),**kwargs)
    d={k:last['counters'][k]-first['counters'][k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}
    source['body_coverage']=source['relay_unique_body_bytes']/d['bytes']
    # Separate captures have unsynchronised clocks: this ratio is diagnostic,
    # not a precise simultaneous frame-loss measurement.
    source['offline_reference_body_ratio']=source['relay_unique_body_bytes']/receiver['relay_unique_body_bytes'] if receiver['relay_unique_body_bytes'] else None
    idle=[r for r in rows if r['wall_ns']/1e9<client['start_wall']-.3]
    idle_fraction=(idle[-1]['counters']['busy_s']-idle[0]['counters']['busy_s'])/(idle[-1]['counters']['active_s']-idle[0]['counters']['active_s']) if len(idle)>1 else None
    drops={h:(folder/h/'air.pcap.capture.log').read_text() for h in ['4','5']}
    server=json.loads((folder/'5/server.json').read_text())
    intervals=[stream for interval in server.get('intervals',[]) for stream in interval.get('streams',[])]
    seconds=sum(row['seconds'] for row in intervals)
    result={'name':folder.name,'source_visible':source,'offline_receiver_reference':receiver,'source_delta':d,'idle_busy_fraction':idle_fraction,
            'tx_rate_Bps':statistics.median(r['counters']['tx_bps']/8 for r in selected),'capture_logs':drops,
            'receiver_bps':8*sum(row['bytes'] for row in intervals)/seconds if seconds else None,
            'source_begin':first,'source_end':last,'scope':'sender inputs only for fitting; receiver capture excluded from model features; CCMP exclusive reader assumption'}
    (folder/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    profile_path=folder.parent/'frozen_sender_profile_v2.json'
    if not profile_path.exists():profile_path=folder.parent/'frozen_sender_profile.json'
    if profile_path.exists() and folder.name.startswith('validation'):
        p=json.loads(profile_path.read_text())
        def sample(row):
            return dict(row['counters'],boot_id='offline-same-run',AP=p['AP'],frequency_MHz=p['frequency_MHz'],width_MHz=p['width_MHz'],tx_Bps=row['counters']['tx_bps']/8)
        try:verdict=estimate(p,sample(first),sample(last),source);result['sender_estimate']=verdict;result['self_pass']=abs(verdict['beta'])<=.05 if not folder.name.startswith('validationB2') else None
        except ValueError as e:result['sender_estimate_error']=str(e);result['self_pass']=False
        result['frozen_profile_sha256']=__import__('hashlib').sha256(profile_path.read_bytes()).hexdigest()
        (folder/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--labels',nargs='+',required=True);a=p.parse_args()
    for label in a.labels:
        r=trial(ROOT/'runs'/a.run/label)
        print(json.dumps({k:r[k] for k in ['name','source_delta','idle_busy_fraction','receiver_bps']}|{'visible':{k:r['source_visible'][k] for k in ['relay_rate_Bps','relay_wire_bytes','body_coverage','offline_reference_body_ratio','amsdu_frames','shared_ampdu_refs','ambiguous_amsdu_body_bytes']},'sender_estimate':r.get('sender_estimate'),'error':r.get('sender_estimate_error'),'self_pass':r.get('self_pass')}),flush=True)


if __name__=='__main__':main()
