"""Extract trace evidence, source findings and conditional link-model inputs."""
import json,re,statistics,csv
from pathlib import Path
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.model import identify_overhead

def main():
    base=ROOT/'runs/w1_20261012_163000';cal=base/'calibration_ready'
    summary=json.loads((cal/'summary.json').read_text());measurements={}
    for name in ['udp1','udp2','udp3','tcp']:
        hosts={}
        for h in ['12','10']:
            rows=[json.loads(s) for s in (cal/(name+'_'+h+'_telemetry.jsonl')).read_text().splitlines()]
            wireless=[r['wireless'] for r in rows]
            hosts[h]={'tx_PHY_Mbps_median':statistics.median(r.get('tx_Bps',0)*8/1e6 for r in wireless),
              'rx_PHY_Mbps_median':statistics.median(r.get('rx_Bps',0)*8/1e6 for r in wireless),
              'retries_delta':wireless[-1]['retries']-wireless[0]['retries'],
              'packets_delta':wireless[-1]['packets']-wireless[0]['packets'],
              'bytes_delta':wireless[-1]['bytes']-wireless[0]['bytes'],
              'udp_delta':{k:rows[-1]['udp_global'][k]-rows[0]['udp_global'][k] for k in rows[0]['udp_global']}}
        measurements[name]=hosts
    a=measurements['udp3']['12'];down=measurements['udp3']['10']['rx_PHY_Mbps_median']
    retry=a['retries_delta']/a['packets_delta']
    o=identify_overhead(summary['C0_UDP_receiver_median_bps']/8,a['tx_PHY_Mbps_median']*125000,down*125000,retry,1400,0)
    result={'calibration_wireless':measurements,
      'conditional_O_s':o,'conditional_O_inputs':{'UDP_payload_bytes':1400,'header_bytes':0,'retry_ratio':retry,'Rup_Mbps':a['tx_PHY_Mbps_median'],'Rdown_Mbps':down},
      'O_qualification':'Effective fit to iperf3 UDP, not identified intrinsic 802.11 fixed cost: packet batching/offload and external occupancy not isolated; no active/busy/tx counters. Sender rx bitrate is AP-to-sender and cannot replace AP-to-receiver bitrate; actual host10 rx used here.',
      'hand_example':{'C_Bps':25000000,'L_Bps':10485760,'alpha':.9,'c_Bps':22500000,'recovery_upper_bytes':12014240,'whole_1MiB_samples':11,'proposal_samples':13,
       'finding':'Proposal 13MiB example uses C-L; applying paced alpha*C-L permits 11MiB. Prototype also floors receive socket at1MiB and reserves a full-sample/repair fq margin, so its output differs from the printed98KiB/0.96MiB/flow67 example.'},
      'source_findings':[
       {'source':'FastDDS_UDPTransportInterface.cpp','line':522,'finding':'Blocking socket send uses SO_SNDTIMEO; would_block/try_again branch drops the datagram and returns true. UdpSndbufErrors=0 alone cannot establish wait-only delivery semantics.'},
       {'source':'Cyclone_ddsi_udp.c','line':162,'finding':'Linux uses blocking UDP sockets; sendmsg errors INTERRUPTED/TRY_AGAIN are retried, other errors may return-1. Actual errors and timeout must be retained.'},
       {'source':'Linux_sch_fq.c','line':375,'finding':'Unconnected UDP (TCP_CLOSE) is classified by packet hash/destination, even with one send socket. Socket count alone does not establish fq flow count.'},
       {'source':'Linux_sch_fq.c','line':1121,'finding':'Default flow_plimit=100 in upstream Linux6.8; installed-kernel effective qdisc parameters recorded in traces.'},
       {'source':'Linux_rtw89_mac80211.c','line':1,'finding':'Upstream Linux6.8 rtw89 ieee80211_ops lacks get_survey; actual both root survey dumps empty. Counters are missing, not zero.'},
       {'source':'FastDDS_RTPSParticipantImpl.cpp','line':81,'finding':'v2.6.11 explicitly parses FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA. The corresponding supported runtime behavior must be verified by TCP sockets/capture.'},
       {'source':'FastDDS_WriterTimes.h','line':62,'finding':'Default heartbeatPeriod.seconds=3 in v2.6.11 source.'}],
      'backpressure':{}}
    for p in base.glob('*_bp_*/summary.json'):
        r=json.loads(p.read_text());pub=json.loads((p.parent/'12/pub.json').read_text());telem=[json.loads(s) for s in (p.parent/'12/telemetry.jsonl').read_text().splitlines()]
        pk=pub.get('measurement_started_ns',0)/1e9;pe=pub.get('measurement_ended_ns',0)/1e9
        classes=[]
        for row in csv.DictReader((p.parent/'12/govern.csv').open()):
            for c in json.loads(row['class_json']):
                if c.get('handle')=='7ac0:10':classes.append((float(row['monotonic_s']),c['bytes']))
        steady=[(t,b) for t,b in classes if pk+3<=t<=pe-1]
        rate=8*(steady[-1][1]-steady[0][1])/(steady[-1][0]-steady[0][0])/1e6 if len(steady)>1 else None
        sockets=[]
        for row in telem:
            if pk<=row['monotonic_s']<=pe:
                # Preserve exact max send-accounting sample including endpoint/PID.
                raw=row['sockets']['stdout']
                for block in raw.split('UNCONN')[1:]:
                    if '"python3"' in block:
                        t=re.search(r'\bt(\d+)',block);tb=re.search(r'\btb(\d+)',block)
                        if t and tb:sockets.append({'t':int(t[1]),'tb':int(tb[1]),'monotonic_s':row['monotonic_s'],'raw':'UNCONN'+block})
        result['backpressure'][r['name']]={'steady_HTB_class_Mbps':rate,'configured_HTB_Mbps':r['config']['cap_packet_Bps']*8/1e6,'max_socket_sample':max(sockets,key=lambda x:x['t'],default=None),
          'metrics':r['metrics'],'telemetry':r['telemetry'],'restored_qdisc':r['qdisc_after']}
    (base/'evidence.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'conditional_O_us':o*1e6,'backpressure':{k:{'HTB_Mbps':v['steady_HTB_class_Mbps'],'socket_t':v['max_socket_sample']['t'] if v['max_socket_sample'] else None} for k,v in result['backpressure'].items()}},indent=2))

if __name__=='__main__':main()
