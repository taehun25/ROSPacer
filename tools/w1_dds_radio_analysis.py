"""Evaluate frozen packet geometry on DDS radio windows; no latency inference."""
import argparse
import json
from pathlib import Path
import statistics
from deploy import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--label',default='dds_radio_v2');a=p.parse_args()
    base=ROOT/'runs'/a.run;folder=base/a.label;profile=json.loads((base/'frozen_radio_profile_v3_packet.json').read_text());results=[]
    for dir in sorted(folder.iterdir()):
        if not dir.is_dir() or not (dir/'summary.json').exists():continue
        t=json.loads((dir/'summary.json').read_text());pub=json.loads((dir/'4/pub.json').read_text());a4=json.loads((dir/'4/radio.json').read_text())['rows'];a5=json.loads((dir/'5/radio.json').read_text())['rows']
        lo=pub['measurement_started_ns']/1e9+2;hi=pub['measurement_ended_ns']/1e9-2
        rows=[r for r in a4 if lo<=r['mono_s']<=hi]
        if len(rows)<2:raise ValueError('insufficient radio span')
        walllo,wallhi=rows[0]['wall_ns'],rows[-1]['wall_ns'];rec=[r for r in a5 if walllo<=r['wall_ns']<=wallhi]
        first,last=rows[0]['counters'],rows[-1]['counters'];d={k:last[k]-first[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']};elapsed=d['active_s'];n=d['packets'];mean=d['bytes']/n;ip=mean-profile['station_link_header_bytes']
        down=statistics.median(r['counters']['rx_bps'] for r in rec)/8;up=statistics.median(r['counters']['tx_bps'] for r in rows)/8;nu=d['retries']/n
        relay=n*(profile['O_down_s']+ip/down);beta=(d['busy_s']-profile['idle_busy_fraction']*elapsed-relay)/elapsed
        theta=((1+nu)*(profile['O_up_s']+ip/up)+profile['O_down_s']+ip/down)/mean
        etx,ety=rec[0].get('etstats',{}),rec[-1].get('etstats',{});namp=(ety.get('rx_ampdu_cnt',0)-etx.get('rx_ampdu_cnt',0))%(2**32);nrx=ety.get('rx_packets',0)-etx.get('rx_packets',0)
        actual=pub['succeeded']*1048576*8/((pub['measurement_ended_ns']-pub['measurement_started_ns'])/1e9)
        r={**t,'delta':d,'mean_station_frame_bytes':mean,'mean_IP_bytes':ip,'receiver_RX_PHY_Mbps':down*8/1e6,'sender_TX_PHY_Mbps':up*8/1e6,'beta_unclipped':beta,'candidate_cap_skb_Mbps':.9*(1-beta)/theta*8/1e6,
           'actual_publish_payload_Mbps':actual,'RX_MSDU_per_AMPDU':nrx/namp if namp else None,'input_candidate_pass':abs(beta)<=.05 and all(t['runtime_valid'].values()) and t['received']==t['succeeded'] and t['publisher_error'] is None and t['subscriber_error'] is None,'latency_qualified':False}
        results.append(r)
    output={'rows':results,'all_input_candidate_pass':len(results)==6 and all(r['input_candidate_pass'] for r in results),'profile':'frozen_radio_profile_v3_packet.json','normal_adaptive_qualified':False}
    (folder/'analysis.json').write_text(json.dumps(output,indent=2));print(json.dumps({'all_input_candidate_pass':output['all_input_candidate_pass'],'rows':[{k:r[k] for k in ['name','planned','succeeded','received','beta_unclipped','RX_MSDU_per_AMPDU','input_candidate_pass','actual_publish_payload_Mbps']} for r in results]}))


if __name__=='__main__':main()
