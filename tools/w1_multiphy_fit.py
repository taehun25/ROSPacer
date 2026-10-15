"""Fit and freeze provisional candidate from training only, never validation."""
import hashlib,json,math,statistics
from pathlib import Path
from deploy import ROOT
BASE=ROOT/'runs/w1_20261014_sender_multiphy'

def nnls2(xs,ys):
    aa=sum(a*a for a,b in xs);bb=sum(b*b for a,b in xs);ab=sum(a*b for a,b in xs)
    ay=sum(a*y for (a,b),y in zip(xs,ys));by=sum(b*y for (a,b),y in zip(xs,ys));det=aa*bb-ab*ab
    if min(aa,bb)<=0 or det/(aa*bb)<1e-6:raise ValueError('exchange calibration not identifiable')
    candidates=[(max(0,ay/aa),0),(0,max(0,by/bb)),(0,0)]
    unconstrained=((ay*bb-by*ab)/det,(by*aa-ay*ab)/det)
    if min(unconstrained)>=0:candidates.append(unconstrained)
    best=min(candidates,key=lambda k:sum((y-k[0]*a-k[1]*b)**2 for (a,b),y in zip(xs,ys)))
    return best,det/(aa*bb)

def eligible(w,conservation):
    v=w['visible']
    if w.get('capture_drops_max',0) or v['unknown_rate_body_bytes'] or not w['down_Bps']:return False
    if conservation:return .25<=w['body_coverage']<=1.1 and v['counts'].get('own_relay_mpdu',0)>=128 and v['counts'].get('peer_ba',0)>=32
    return w['usable_features']

def main():
    tags=['train_strong_50','train_strong_150','train_strong_sat','train_mid_50','train_mid_150','train_mid_sat','dds_train_fastdds','dds_train_cyclonedds']
    data=[json.loads((BASE/t/'features.json').read_text()) for t in tags]
    if any(any(r['receiver_udp_errors'].values()) for r in data):raise ValueError('training receive buffer error')
    idle=statistics.median(r['idle_busy_fraction'] for r in data if r['idle_busy_fraction'] is not None)
    old=json.loads((ROOT/'runs/w1_20261013_sender_only/frozen_sender_profile_v2.json').read_text())
    for conservation,name in [(False,'frozen_direct.json'),(True,'frozen_profile.json')]:
        target=BASE/name
        if target.exists():raise ValueError('preserve frozen candidate')
        xs=[];ys=[];selected=[]
        for r in data:
            for w in r['windows']:
                if not eligible(w,conservation):continue
                d=w['delta'];v=w['visible'];dt=d['active_s']
                serial=d['bytes']/w['down_Bps'] if conservation else v['relay_serialization_s']
                xs.append((v['counts'].get('own_ba',0)/dt,v['counts'].get('peer_ba',0)/dt));ys.append((d['busy_s']-serial)/dt-idle);selected.append((r['tag'],w))
        if len(xs)<6:raise ValueError('insufficient independent calibration windows')
        costs,rank=nnls2(xs,ys)
        # A symmetric conditional per-packet cost remains an explicit assumption.
        # Capacity training references are fresh saturation tests only.
        Os=[];c0s=[]
        for r in data:
            if r['requested_Mbps']!=0 or not r['receiver_payload_Bps']:continue
            C0=r['receiver_payload_Bps'];c0s.append(C0)
            for w in r['windows']:
                # PHY sampling eligibility applies to capacity fitting even for direct candidate;
                # it does not promote missing relay byte observations to direct input success.
                if not eligible(w,True):continue
                nu=w['delta']['retries']/w['delta']['packets']
                O=(1400/C0-(1+nu)*1428/w['up_Bps']-1428/w['down_Bps'])/(2+nu)
                if O<=0:raise ValueError('nonpositive conditional packet cost')
                Os.append(O)
        if len(Os)<6:raise ValueError('insufficient capacity calibration PHY windows')
        C0=statistics.median(c0s);O=statistics.median(Os)
        phy_selected=[w for r in data for w in r['windows'] if eligible(w,True)]
        up=[w['up_Bps']*8/1e6 for w in phy_selected];down=[w['down_Bps']*8/1e6 for w in phy_selected]
        p={**old,'validated':False,'uplink_sampling':'window-byte-retry-harmonic','uplink_Mbps_range':[min(up)-1,max(up)+1],'downlink_Mbps_range':[min(down)-1,max(down)+1],
           'BA_busy_s':costs[0],'relay_exchange_busy_s':costs[1],'idle_busy_fraction':idle,'O_up_s':O,'O_down_s':O,'cap_ceiling_skb_Bps':.9*C0,
           'capacity_reference':{'C0_Bps':C0,'source':'fresh train_*_sat receiver interval goodput; no validation data'},
           'training_sha256':{r['tag']:hashlib.sha256((BASE/r['tag']/'features.json').read_bytes()).hexdigest() for r in data},
           'fit_rank_fraction':rank,'coefficient_units':'operating proxy costs, not intrinsic physical BA/PPDU airtime','fit_window_count':len(xs),
           'capacity_fit_count':len(Os),'capacity_O_range_us':[min(Os)*1e6,max(Os)*1e6],
           'training_residuals':[{'tag':tag,'beta_raw':y-costs[0]*x[0]-costs[1]*x[1]} for (tag,w),x,y in zip(selected,xs,ys)],
           'limitations':old['limitations']+['Scope bounds are observed harmonic PHY windows with1Mb/s numeric margin, not unmeasured low-PHY coverage.','Receiver counter/data used only offline to check conservation; no online receiver feedback.','Two physical positions only; further movement unavailable.','Candidates still unapproved until held-out validation and stability checks.']}
        if conservation:p.update(relay_estimator='source-station-byte-conservation-v1',PHY_sample_min_frames=128,PHY_sample_body_coverage=[.25,1.1],peer_BA_min_count=32,relay_byte_assumption='source station TX bytes approximate own forwarded wire bytes; requires exclusive peer and offline loss/buffer/conservation checks')
        target.write_text(json.dumps(p,indent=2));print(json.dumps({'candidate':name,'windows':len(xs),'rank':rank,'exchange_us':[x*1e6 for x in costs],'O_us':O*1e6,'C0_Mbps':C0*8/1e6,'up_scope':p['uplink_Mbps_range'],'down_scope':p['downlink_Mbps_range'],'training_abs_beta_p95':sorted(abs(x['beta_raw']) for x in p['training_residuals'])[math.ceil(.95*len(xs))-1],'approved':False}),flush=True)
    receipt={n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in ['frozen_direct.json','frozen_profile.json']};(BASE/'freeze_receipt.json').write_text(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
