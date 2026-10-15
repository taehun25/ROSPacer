import csv,json,sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.metrics import analyze_pair
BASE=ROOT/'runs/w1_20261014_ack_live'
def main():
    results=[]
    for tag in ['minphy_c2_fast','minphy_c2_cyclone']:
        if not (BASE/tag/'summary.json').exists() and (BASE/(tag+'_r2')/'summary.json').exists():tag=tag+'_r2'
        if not (BASE/tag/'summary.json').exists() and (BASE/(tag+'_r1')/'summary.json').exists():tag=tag+'_r1'
        f=BASE/tag
        if not (f/'summary.json').exists():continue
        r=json.loads((f/'summary.json').read_text());pub=json.loads((f/'4/pub.json').read_text());sub=json.loads((f/'5/sub.json').read_text());r['metrics']=analyze_pair(pub,sub);rows=list(csv.DictReader((f/'4/live/trace.csv').open()));r['cap_Mbps_range']=[min(float(x['cap_packet_Bps'])*8/1e6 for x in rows),max(float(x['cap_packet_Bps'])*8/1e6 for x in rows)];r['updated_rows']=sum(x['status']=='updated' for x in rows);r['source_rows']=len(rows)
        steady=[x for x in rows if pub['measurement_started_ns']/1e9+3<=float(x['monotonic_s'])<=pub['measurement_ended_ns']/1e9-1];r['steady_update_fraction']=sum(x['status']=='updated' for x in steady)/len(steady) if steady else 0
        fq=[q for x in rows for q in json.loads(x['qdisc_json']) if q['kind']=='fq'];r['fq_drops']=max(q['drops'] for q in fq);r['fq_backlog_max']=max(q['backlog'] for q in fq)
        bg=BASE/(tag+'_background')
        if (bg/'12_client.json').exists():
            raw=json.loads((bg/'12_client.json').read_text());client=json.loads(raw['stdout']);server=json.loads((bg/'10_server.json').read_text());r['competitor_rc']=raw['rc']
            for label,record in [('tx',client),('rx',server)]:
                items=[s for interval in record['intervals'] for s in interval['streams']];seconds=sum(s['seconds'] for s in items);r['competitor_'+label+'_Mbps']=8*sum(s['bytes'] for s in items)/seconds/1e6 if seconds else None
        results.append(r)
    (BASE/'minphy_live_results.json').write_text(json.dumps({'results':results,'formal_performance_approved':False,'receiver_stats_daemon':False,'original_beta_decomposition_approved':False},indent=2));print(json.dumps([{k:r[k] for k in ['tag','published','received','updates','HTB_changes','cap_Mbps_range','steady_update_fraction','fq_drops']} for r in results]),flush=True)
if __name__=='__main__':main()
