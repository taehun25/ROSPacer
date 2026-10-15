"""Separate CRC rejection, metadata rejection and passive visibility loss."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.sender_radio import pcap_frames,decode,summarize,control_summary

AP='b0:38:6c:7d:f5:74';PEER='3c:0a:f3:02:e4:c7';SOURCE='3c:0a:f3:02:d9:3b'


def inspect(path,start=None,end=None):
    events=[];errors=Counter();counts=Counter();formats=Counter();signals=[];sizes=[];bf=Counter()
    for stamp,packet,wire in pcap_frames(path):
        if start is not None and not start<=stamp<=end:continue
        try:r=decode(packet,wire,allow_bad_fcs=True)
        except ValueError as e:errors[str(e)]+=1;continue
        counts['all_frames']+=1
        if r['kind']==2 and r['subtype'] in (0,8) and r.get('ta')==AP and r['ra']==PEER:
            counts['peer_bad_fcs' if r['bad_fcs'] else 'peer_good_fcs']+=1
            counts['peer_body_bad' if r['bad_fcs'] else 'peer_body_good']+=r['body_bytes']
            counts['unknown_peer_PHY']+=r['rate_Bps'] is None
            formats[str(r.get('he_format'))]+=1;bf[str(r.get('beamformed'))]+=1
            if 'signal_dbm' in r:signals.append(r['signal_dbm'])
            sizes.append(r['wire_bytes']);events.append((stamp,r))
    return {'counts':dict(counts),'errors':dict(errors),'HE_formats':dict(formats),'beamformed':dict(bf),'signal_dbm_median':statistics.median(signals) if signals else None,'median_wire_bytes':statistics.median(sizes) if sizes else None},events


def match(source,receiver):
    # PN is diagnostic only: receiver offload may strip the original CCMP IV.
    # Use header matches to estimate a capture-clock offset, without treating
    # this as chrony/E2E clock qualification or a PPDU airtime observation.
    index=defaultdict(list)
    for stamp,r in receiver:
        if not r['bad_fcs']:index[(r['tid'],r['sequence'])].append((stamp,r))
    candidates=[];hist=Counter()
    for stamp,r in source:
        for target,rr in index[(r['tid'],r['sequence'])]:
            if abs(r['wire_bytes']-rr['wire_bytes'])<=40:
                delta=target-stamp;hist[round(delta/.02)]+=1;candidates.append((stamp,r,target,rr,delta))
    if not candidates:return {'matched_good':0,'matched_bad':0,'reason':'no corresponding MAC headers'}
    bucket=hist.most_common(1)[0][0];offset=statistics.median(c[-1] for c in candidates if abs(c[-1]-bucket*.02)<.021)
    matched=Counter();unique=set();pn=Counter();mismatch=[]
    for stamp,r,target,rr,delta in candidates:
        if abs(delta-offset)>.003:continue
        key=(stamp,r['sequence'],r['tid'])
        if key in unique:continue
        unique.add(key);matched['matched_bad' if r['bad_fcs'] else 'matched_good']+=1
        if r.get('ccmp_pn') is not None and rr.get('ccmp_pn') is not None:pn['same' if r['ccmp_pn']==rr['ccmp_pn'] else 'different']+=1
    return dict(matched,capture_clock_offset_s=offset,PN_comparison=dict(pn),qualification='tentative MAC header/length/time matching; not qualified E2E synchronisation')


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='w1_20261013_sender_gap');p.add_argument('--label',required=True);a=p.parse_args()
    folder=ROOT/'runs'/a.run/a.label;client=json.loads((folder/'client.json').read_text())
    if client['rc']!=0:raise ValueError('failed main traffic is not a valid model/capture comparison')
    rows=json.loads((folder/'4/radio.json').read_text())['rows']
    selected=[r for r in rows if client['start_wall']+1.5<=r['wall_ns']/1e9<=client['end_wall']-1.5]
    first,last=selected[0],selected[-1];start=first['wall_ns']/1e9;end=last['wall_ns']/1e9
    src,events=inspect(folder/'4/air.pcap',start,end);ref,reference=inspect(folder/'5/air.pcap')
    by=last['counters']['bytes']-first['counters']['bytes'];dt=last['counters']['active_s']-first['counters']['active_s']
    own_by=by
    if client.get('origin')=='pc':by=1400*sum(row['packets'] for row in client['send_timeline'] if start<=row['wall']<=end)
    low={k:(last['low_level'].get(k)-first['low_level'].get(k)) if first.get('low_level',{}).get(k) is not None and last.get('low_level',{}).get(k) is not None else None for k in ['dot11FCSErrorCount','dot11ACKFailureCount','dot11RTSFailureCount']}
    result={'name':a.label,'origin':client.get('origin','sender'),'source':src,'receiver_reference':ref,'matching':match(events,reference),'source_bytes':by,'observer_own_wifi_bytes':own_by,'source_active_s':dt,
            'source_tx_fraction':(last['counters']['tx_s']-first['counters']['tx_s'])/dt,
            'busy_fraction':(last['counters']['busy_s']-first['counters']['busy_s'])/dt,
            'good_body_coverage':src['counts'].get('peer_body_good',0)/by,'all_candidate_body_coverage':(src['counts'].get('peer_body_good',0)+src['counts'].get('peer_body_bad',0))/by,
            'low_level_delta':low,'capture_logs':{h:(folder/h/'air.pcap.capture.log').read_text() for h in ['4','5']},
            'scope':'CRC-failed headers are tentative; no change to production estimator acceptance'}
    # Reference capture is offline only. Align its window approximately using
    # good MAC-header matches; counts are NOT exact physical visibility rates.
    offset=result['matching'].get('capture_clock_offset_s',0)
    result['control_diagnostic']={h:control_summary(((t,p,w) for t,p,w in pcap_frames(folder/h/'air.pcap') if start+(offset if h=='5' else 0)<=t<=end+(offset if h=='5' else 0)),AP,PEER) for h in ['4','5']}
    (folder/'gap_analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ['name','source','matching','source_tx_fraction','busy_fraction','good_body_coverage','all_candidate_body_coverage','low_level_delta']}))


if __name__=='__main__':main()
