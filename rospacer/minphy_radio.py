"""Scoped sender survey model with one offline peer PHY calibration input.

Effective per-packet relay overhead is fitted using sender-only self-load data.
It absorbs aggregation/driver effects; it is not physical PPDU airtime or O.
"""
import math

def estimate(profile,old,new):
    if profile['busy_semantics']!='excludes_self_tx':raise ValueError('unqualified busy semantics')
    if old['boot_id']!=new['boot_id'] or old['AP']!=new['AP'] or new['AP']!=profile['AP']:raise ValueError('source identity/AP changed')
    d={k:new[k]-old[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}
    if any(v<0 for v in d.values()):raise ValueError('source counter reset')
    dt=d['active_s'];n=d['packets']
    if dt<=0 or n<=0 or max(d['busy_s'],d['tx_s'])>1.1*dt:raise ValueError('invalid source observation window')
    frame=d['bytes']/n;ip=frame-14;up=new.get('window_tx_Bps',new['tx_Bps']);down=profile['peer_rx_phy_Bps']
    if not 28<=ip<=1500 or not math.isfinite(up) or up<=0 or not math.isfinite(down) or down<=0:raise ValueError('invalid packet/PHY geometry')
    retry=d['retries']/n
    relay=profile['relay_tx_scale']*d['tx_s']*up/down/(1+retry) if profile.get('relay_model')=='scaled_sender_tx_duration' else n*(profile['relay_effective_overhead_s']+ip/down)
    beta=(d['busy_s']-profile['idle_busy_fraction']*dt-relay)/dt
    if not -.05<=beta<=1:raise ValueError('occupancy residual outside accepted range')
    o=profile['service_effective_overhead_s']
    theta=((1+retry)*(o/2+ip/up)+o/2+ip/down)/frame
    raw=(1-beta)/theta
    if not math.isfinite(raw) or raw<=0:raise ValueError('invalid source service budget')
    return dict(beta=beta,relay_s=relay,theta=theta,raw_packet_Bps=raw,cap_packet_Bps=min(profile['ceiling_packet_Bps'],profile['alpha']*raw),raw_UDP_payload_Mbps=raw*1400/frame*8/1e6,mean_station_bytes=frame,uplink_Mbps=up*8/1e6,downlink_Mbps=down*8/1e6)

def fit(idle_pairs,self_pairs,capacity_payload_Bps,capacity_pair,peer_phy,AP):
    idle=sum(b['busy_s']-a['busy_s'] for a,b in idle_pairs)/sum(b['active_s']-a['active_s'] for a,b in idle_pairs)
    numerator=denominator=0
    for a,b in self_pairs:
        n=b['packets']-a['packets'];by=b['bytes']-a['bytes'];dt=b['active_s']-a['active_s'];busy=b['busy_s']-a['busy_s']
        if min(n,dt)<=0:continue
        numerator+=n*(busy-idle*dt-(by-14*n)/peer_phy);denominator+=n*n
    if denominator<=0:raise ValueError('no self-load calibration')
    relay=numerator/denominator
    a,b=capacity_pair;n=b['packets']-a['packets'];frame=(b['bytes']-a['bytes'])/n;ip=frame-14;retry=(b['retries']-a['retries'])/n;up=b['tx_Bps'];service=(1400/capacity_payload_Bps-(1+retry)*ip/up-ip/peer_phy)/(1+retry/2)
    if min(relay,service)<0 or not all(math.isfinite(x) for x in [idle,relay,service]):raise ValueError('negative/inconsistent effective calibration')
    return dict(AP=AP,busy_semantics='excludes_self_tx',idle_busy_fraction=idle,relay_effective_overhead_s=relay,service_effective_overhead_s=service,peer_rx_phy_Bps=peer_phy,capacity_payload_Bps=capacity_payload_Bps,ceiling_packet_Bps=.9*capacity_payload_Bps*frame/1400,alpha=.9,validated=False,receiver_feedback_daemon=False,scope='fixed AP/channel149/80; MT7921; one sender flow; offline peer PHY; effective per-packet operating costs, not intrinsic physical airtime')
