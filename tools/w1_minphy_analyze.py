"""Freeze effective source model from calibration, then evaluate new trials."""
import argparse,hashlib,json,statistics,sys,time
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.minphy_radio import fit,estimate
BASE=ROOT/'runs/w1_20261014_ack_live'
def pairs(tag,idle=False):
    record=json.loads((BASE/tag/'4/source.json').read_text());rows=record['rows'];result=[]
    for i,b in enumerate(rows):
        if not idle and not record['start_monotonic']+4<=b['monotonic_s']<=record['end_monotonic']-2:continue
        previous=[a for a in rows[:i] if b['monotonic_s']-a['monotonic_s']>=3]
        if previous:result.append((previous[-1],b))
    return result
def rate(tag):
    r=json.loads((BASE/tag/'5/server.json').read_text());items=[s for interval in r['intervals'] for s in interval['streams']];seconds=sum(s['seconds'] for s in items)
    if not seconds:raise ValueError('receiver iperf interval missing')
    return 8*sum(s['bytes'] for s in items)/seconds/1e6
def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',action='store_true');p.add_argument('--v2',action='store_true');a=p.parse_args()
    if a.fit:
        path=BASE/'minphy_frozen_profile.json'
        if path.exists():raise ValueError('preserve frozen profile')
        down=json.loads((BASE/'peer_phy_calibration.json').read_text())['downlink_PHY_Bps'];cap=rate('minphy_cal_sat')*1e6/8;ps=pairs('minphy_cal_sat');first,last=ps[0][0],ps[-1][1]
        profile=fit(pairs('minphy_cal_idle',True),pairs('minphy_cal50')+pairs('minphy_cal150')+ps,cap,(first,last),down,'b0:38:6c:7d:f5:74');profile['registered_UTC']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());profile['kernel_modules']=json.loads((BASE/'module_baseline.json').read_text());profile['source_sha256']=hashlib.sha256((ROOT/'rospacer/minphy_radio.py').read_bytes()).hexdigest();path.write_text(json.dumps(profile,indent=2));print(json.dumps(profile),flush=True);return
    profile_path=BASE/('minphy_frozen_profile_v2.json' if a.v2 else 'minphy_frozen_profile.json');profile=json.loads(profile_path.read_text());results=[]
    tags=['minphy_validation_clean','minphy_validation_B2','minphy_validation_C2']
    if a.v2:tags=[t+'_v2' for t in tags]
    for tag in tags:
        if not (BASE/tag/'4/source.json').exists() and (BASE/(tag+'_r1')/'4/source.json').exists():tag=tag+'_r1'
        if not (BASE/tag/'4/source.json').exists():continue
        valid=[];errors={};ps=pairs(tag)
        source_rows=json.loads((BASE/tag/'4/source.json').read_text())['rows']
        for x,y in ps:
            if a.v2:
                from rospacer.sender_radio import window_uplink
                y={**y,'window_tx_Bps':window_uplink([r for r in source_rows if x['monotonic_s']<=r['monotonic_s']<=y['monotonic_s']],14)}
            try:valid.append(estimate(profile,x,y))
            except (ValueError,KeyError) as e:errors[str(e)]=errors.get(str(e),0)+1
        measured=rate(tag);predicted=statistics.median(x['raw_UDP_payload_Mbps'] for x in valid) if valid else None;error=abs(predicted-measured)/measured if predicted is not None and measured else None;usable=len(valid)/len(ps) if ps else 0
        clean_beta_abs_p95=sorted(abs(x['beta']) for x in valid)[int(.95*(len(valid)-1))] if valid else None
        r={'tag':tag,'eligible_windows':len(ps),'valid_windows':len(valid),'usable_fraction':usable,'hold_reasons':errors,'predicted_payload_Mbps':predicted,'receiver_interval_Mbps':measured,'relative_error':error,'beta_median':statistics.median(x['beta'] for x in valid) if valid else None,'beta_abs_p95':clean_beta_abs_p95,'clean_occupancy_near_zero':clean_beta_abs_p95<=.05 if 'clean' in tag and clean_beta_abs_p95 is not None else None,'pass':usable>=.95 and error is not None and error<=.2,'receiver_online_feedback':False};results.append(r)
    qualified=len(results)==3 and all(r['pass'] for r in results)
    (BASE/('minphy_validation_v2.json' if a.v2 else 'minphy_validation.json')).write_text(json.dumps({'results':results,'capacity_budget_gate_pass':qualified,'qualified_in_completed_scope':qualified and all(r['clean_occupancy_near_zero'] is not False for r in results),'original_beta_decomposition_qualified':False,'all_three_completed':len(results)==3,'refit_after_validation':False,'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest()},indent=2));print(json.dumps(results),flush=True)
if __name__=='__main__':main()
