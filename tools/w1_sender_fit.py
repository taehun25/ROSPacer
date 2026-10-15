"""Freeze an explicitly provisional sender-only operating profile."""
import hashlib
import json
from pathlib import Path
import statistics
from deploy import ROOT


def main():
    base=ROOT/'runs/w1_20261013_sender_only'
    data=[json.loads((base/n/'analysis.json').read_text()) for n in ['calibration30','calibration100','calibration200']]
    idle=statistics.median(r['idle_busy_fraction'] for r in data)
    # Serialization coefficient is fixed to one. Fit nonnegative exchange
    # costs to source busy, with no receiver counters or capture features.
    xs=[];ys=[]
    for r in data:
        v=r['source_visible'];d=r['source_delta']
        xs.append((v['counts']['own_ba'],v['counts']['peer_ba']))
        ys.append(d['busy_s']-idle*d['active_s']-v['relay_serialization_s'])
    aa=sum(x*x for x,z in xs);bb=sum(z*z for x,z in xs);ab=sum(x*z for x,z in xs)
    ay=sum(x*y for (x,z),y in zip(xs,ys));by=sum(z*y for (x,z),y in zip(xs,ys));det=aa*bb-ab*ab
    if det<=0:raise ValueError('unidentifiable sender exchange calibration')
    costs=((ay*bb-by*ab)/det,(by*aa-ay*ab)/det)
    if min(costs)<0:raise ValueError('negative operating exchange coefficient')
    reference=ROOT/'runs/w1_20261013_radio_input_retry/native_adaptive_final/qualified_input_profile.json'
    old=json.loads(reference.read_text());c0=old['cap_ceiling_skb_Bps']/.9
    up=statistics.median(r['tx_rate_Bps'] for r in data);down=statistics.median(r['source_visible']['relay_rate_Bps'] for r in data)
    retry=statistics.median(r['source_delta']['retries']/r['source_delta']['packets'] for r in data)
    overhead=(1400/c0-(1+retry)*1428/up-1428/down)/(2+retry)
    if overhead<=0:raise ValueError('nonpositive conditional capacity overhead')
    p={k:old[k] for k in ['kernel_release','module_srcversions','reader_sha256','AP','frequency_MHz','width_MHz']}
    p.update(validated=False,payload_bytes=1048576,source_MAC='3c:0a:f3:02:d9:3b',receiver_MAC='3c:0a:f3:02:e4:c7',exclusive_receiver=True,
             foreign_peer_frames_max=32,body_coverage_range=[.80,1.10],downlink_Mbps_range=[1195,1205],BA_busy_s=costs[0],relay_exchange_busy_s=costs[1],relay_serialization_scale=1,
             idle_busy_fraction=idle,O_up_s=overhead,O_down_s=overhead,alpha=.9,cap_ceiling_skb_Bps=.9*c0,
             capacity_reference={'C0_Bps':c0,'path':str(reference.relative_to(ROOT)),'sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'note':'existing UDP throughput reference; not newly measured with sender monitor'},
             training_sha256={r['name']:hashlib.sha256((base/r['name']/'analysis.json').read_bytes()).hexdigest() for r in data},
             limitations=['Only one large-data source for receiver MAC. Encrypted A-MSDU inner sources unavailable.',
                          'Effective BlockAck exchange coefficients, not physical BA durations or PPDU counts.',
                          'Symmetric O split assumed; intrinsic up/down overhead not independently identified.',
                          'Initial proof-of-concept only; no held-out B2/C2 or PHY-change qualification yet.'])
    residuals=[]
    for r in data:
        v=r['source_visible'];d=r['source_delta']
        beta=(d['busy_s']-idle*d['active_s']-v['relay_serialization_s']-costs[0]*v['counts']['own_ba']-costs[1]*v['counts']['peer_ba'])/d['active_s']
        residuals.append({'name':r['name'],'beta_raw':beta})
    p['training_residuals']=residuals
    path=base/'frozen_sender_profile.json'
    if path.exists():raise ValueError('preserve frozen profile')
    path.write_text(json.dumps(p,indent=2),encoding='utf8')
    print(json.dumps({'BA_exchange_us':costs[0]*1e6,'DL_exchange_us':costs[1]*1e6,'conditional_O_us':overhead*1e6,'training_residuals':residuals,'validated':False}))


if __name__=='__main__':main()
