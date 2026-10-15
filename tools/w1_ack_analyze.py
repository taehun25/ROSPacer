"""Offline ACK correctness and actual offered-load/performance comparison."""
import csv,json,sys
from pathlib import Path
from deploy import ROOT
from w1_protocol_analyze import app_sequences
sys.path.insert(0,str(ROOT))
from rospacer.metrics import analyze_pair,percentile
BASE=ROOT/'runs/w1_20261014_ack_live'

def main():
    results=[]
    for folder in sorted(BASE.iterdir()):
        if not folder.is_dir() or not (folder/'summary.json').exists() or not (folder/'4/pub.json').exists() or not (folder/'4/protocol/summary.json').exists():continue
        r=json.loads((folder/'summary.json').read_text());pub=json.loads((folder/'4/pub.json').read_text());sub=json.loads((folder/'5/sub.json').read_text());o=json.loads((folder/'4/protocol/summary.json').read_text());rows=list(csv.DictReader((folder/'4/protocol/trace.csv').open()))
        mapping,mismatch=app_sequences(folder/'4/protocol/ethernet.pcap');received={x['seq'] for x in sub['records']};confirmed={mapping[n] for n in o['confirmed_sequence_numbers'] if n in mapping};missing=[n for n in o['observed_sequence_numbers'] if n not in mapping]
        metrics=analyze_pair(pub,sub);caps=[float(x['applied_packet_Bps'])*8/1e6 for x in rows];qs=[q for row in rows for q in json.loads(row['qdisc_json']) if q['kind']=='fq'];cs=[c for row in rows for c in json.loads(row['class_json']) if c['handle']=='7ac0:10'];lags=[float(x['recent_ack_lag_s_max']) for x in rows if x['recent_ack_lag_s_max'] and float(x['recent_ack_lag_s_max'])>0]
        r.update(metrics=metrics,confirmed_receiver_fraction=len(confirmed&received)/len(received) if received else 0,observed_published_fraction=r['observed']/r['published'] if r['published'] else 0,false_confirmation_sequences=sorted(confirmed-received),receiver_unconfirmed_sequences=sorted(received-confirmed),mapping_missing=missing,mapping_inconsistent=mismatch,
                 applied_cap_Mbps_range=[min(caps),max(caps)],applied_final_Mbps=caps[-1],fq_backlog_bytes_max=max([q['backlog'] for q in qs]+[0]),fq_drops=max([q['drops'] for q in qs]+[0]),
                 htb_class_bytes=max([c['bytes'] for c in cs]+[0]),ack_lag_window_max_p95_s=percentile(lags,.95),
                 input_gate_pass=not (confirmed-received) and not missing and not mismatch and r['capture_drops']==0 and r['scope_error'] is None and r['confirmed']>=.95*r['received'] and r['observed']>=.95*r['published'] and r['qdisc_restored'] and all(r['runtime_valid'].values()),
                 sender_only_wireless_capacity_estimate=False,receiver_feedback_daemon=False)
        bg=BASE/(folder.name+'_background')
        if (bg/'12_client.json').exists():
            raw=json.loads((bg/'12_client.json').read_text());client=json.loads(raw['stdout']);server=json.loads((bg/'10_server.json').read_text());inv=json.loads((bg/'inventory.json').read_text())
            def interval_rate(record):
                items=[s for interval in record['intervals'] for s in interval['streams']];seconds=sum(s['seconds'] for s in items)
                return (8*sum(s['bytes'] for s in items)/seconds/1e6 if seconds else None),seconds
            tx,ts=interval_rate(client);rx,rs=interval_rate(server)
            r['competition']={'kind':inv['kind'],'tx_Mbps':tx,'rx_Mbps':rx,'lost_percent':server['end'].get('sum',{}).get('lost_percent'),'duration_s':ts,'receiver_duration_s':rs,'rate_definition':'UDP interval bytes/time; installed server end may incorrectly report zero','sender_AP':inv['nodes']['12']['link'],'receiver_AP':inv['nodes']['10']['link'],'client_rc':raw['rc'],'server_error':server.get('error'),'valid':raw['rc']==0 and tx is not None and tx>0 and rx is not None and rx>0 and ts>=30}
        results.append(r);(folder/'analysis.json').write_text(json.dumps(r,indent=2))
    comparisons=[]
    for kind in ['b2','c2']:
        for mw in ['fast','cyclone']:
            pair={m:next((r for r in results if r['tag']==kind+'_'+mw+'_'+m+'_v2'),None) or next((r for r in results if r['tag']==kind+'_'+mw+'_'+m),None) for m in ['fixed','ack']}
            if not all(pair.values()) or not all(r.get('competition',{}).get('valid') for r in pair.values()):continue
            f,a=pair['fixed'],pair['ack'];fm,am=f['metrics'],a['metrics'];ratio=am['actual_publish_hz']/fm['actual_publish_hz'] if fm['actual_publish_hz'] else None
            comparisons.append({'condition':kind,'DDS':mw,'fixed_tag':f['tag'],'ack_tag':a['tag'],'ACK_input_gate_pass':a['input_gate_pass'],'ACK_over_fixed_publish_rate_ratio':ratio,'fixed_goodput_Mbps':fm['arrival_interval_goodput_Bps']*8/1e6,'ack_goodput_Mbps':am['arrival_interval_goodput_Bps']*8/1e6,'fixed_jitter_p95_ms':fm['arrival_jitter_ms']['p95'],'ack_jitter_p95_ms':am['arrival_jitter_ms']['p95'],'not_formal_superiority':True})
    (BASE/'results.json').write_text(json.dumps({'results':results,'comparisons':comparisons,'formal_performance_qualified':False,'wireless_model_qualified':False},indent=2))
    print(json.dumps([{k:r[k] for k in ['tag','published','received','confirmed','capture_drops','HTB_changes','input_gate_pass','applied_final_Mbps','fq_drops']} for r in results]),flush=True)
if __name__=='__main__':main()
