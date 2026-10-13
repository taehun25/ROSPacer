"""Calibrated MT7921 radio inputs and finite wired receiver feedback.

Calibration is an operating profile, not intrinsic PHY airtime. Missing,
reset, stale or out-of-scope inputs cause a hold; raw beta is never clipped.
"""
import csv
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time


FIELDS=('rx_bytes','rx_packets','rx_mpdu_cnt','rx_ampdu_cnt','rx_ampdu_bytes_cnt','rx_ba_cnt')
U32=set(FIELDS)-{'rx_bytes','rx_packets'}


def snapshot(dev,reader):
    from .linux import observe
    o=observe(dev);q=subprocess.run([reader,dev],capture_output=True,text=True,timeout=4)
    if q.returncode:raise ValueError('native driver statistics unavailable')
    stats=json.loads(q.stdout)['stats']
    o['native']={k:stats[k] for k in FIELDS}
    o['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    m=re.search(r'^Station ([0-9a-f:]{17})',o['station_raw'],re.M)
    o['AP']=m[1] if m else None
    o['observed_wall_ns']=time.time_ns()
    info=subprocess.run(['iw','dev',dev,'info'],capture_output=True,text=True,timeout=4)
    channel=re.search(r'channel (\d+) \((\d+) MHz\), width: (\d+) MHz',info.stdout)
    if not channel:raise ValueError('missing channel scope')
    o['frequency_MHz']=int(channel[2]);o['width_MHz']=int(channel[3])
    for k in ('active_s','busy_s','tx_s','bytes','packets','retries','tx_Bps','rx_Bps'):
        if k not in o:raise ValueError('missing radio input '+k)
    return {k:o[k] for k in ('active_s','busy_s','tx_s','bytes','packets','retries','tx_Bps','rx_Bps','native','boot_id','AP','observed_wall_ns','frequency_MHz','width_MHz')}


def count_delta(first,last,key):
    d=last[key]-first[key]
    if d<0 and key in U32:d+=2**32
    if d<0:raise ValueError('counter reset')
    return d


def check_scope(profile,sample):
    if sample['AP']!=profile['AP']:raise ValueError('AP outside calibrated scope')
    if sample['frequency_MHz']!=profile['frequency_MHz'] or sample['width_MHz']!=profile['width_MHz']:raise ValueError('channel outside calibrated scope')


def estimate(profile,source_old,source_new,receiver_old,receiver_new):
    for old,new in [(source_old,source_new),(receiver_old,receiver_new)]:
        if old['boot_id']!=new['boot_id'] or old['AP']!=new['AP']:raise ValueError('radio identity changed')
        check_scope(profile,new)
    dt=source_new['active_s']-source_old['active_s'];dr=receiver_new['active_s']-receiver_old['active_s']
    if min(dt,dr)<=0:raise ValueError('stale active counter')
    busy=count_delta(source_old,source_new,'busy_s');own=count_delta(source_old,source_new,'tx_s')
    if not 0<=busy<=dt*1.1 or not 0<=own<=dt*1.1:raise ValueError('invalid survey window')
    n=count_delta(source_old,source_new,'packets');by=count_delta(source_old,source_new,'bytes')
    if n<=0:raise ValueError('no own packets in observation window')
    frame=by/n;ip=frame-profile['station_link_header_bytes']
    if not 28<=ip<=1500:raise ValueError('packet geometry outside calibrated IPv4 scope')
    up=source_new['tx_Bps'];down=receiver_new['rx_Bps']
    if min(up,down)<=0:raise ValueError('missing PHY input')
    scale=dt/dr;old,new=receiver_old['native'],receiver_new['native']
    rb=count_delta(old,new,'rx_bytes')*scale;rp=count_delta(old,new,'rx_packets')*scale;mp=count_delta(old,new,'rx_mpdu_cnt')*scale;ap=count_delta(old,new,'rx_ampdu_cnt')*scale;ab=count_delta(old,new,'rx_ampdu_bytes_cnt')*scale
    ratio=ab/rb if rb else 0
    if rb<=0 or ratio>profile['AMPDU_byte_coverage_scale']*1.1:raise ValueError('RX coverage outside calibrated scope')
    coverage=min(1,ab/(profile['AMPDU_byte_coverage_scale']*rb))
    ppdu=ap+mp*(1-coverage)
    ba=count_delta(source_old['native'],source_new['native'],'rx_ba_cnt')
    relay=profile['BA_busy_s']*ba+profile['RX_data_scale']*(rb-14*rp+50*mp)/down+profile['RX_AMPDU_busy_s']*ppdu
    beta=(busy-profile['idle_busy_fraction']*dt-relay)/dt
    if not -.05<=beta<=1:raise ValueError('self/other occupancy residual outside validated range')
    nu=count_delta(source_old,source_new,'retries')/n
    theta=((1+nu)*(profile['O_up_s']+ip/up)+profile['O_down_s']+ip/down)/frame
    rate=profile['alpha']*(1-beta)/theta
    if not math.isfinite(rate) or rate<=0:raise ValueError('invalid capacity estimate')
    return {'beta':beta,'relay_s':relay,'theta':theta,'cap_packet_Bps':min(profile['cap_ceiling_skb_Bps'],rate),'RX_coverage_ratio':ratio,'mean_skb_bytes':frame}


def receiver_feedback(dev,reader,bind,peer,port,seconds,trace):
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((bind,0));end=time.monotonic()+seconds
    try:
        with open(trace,'w') as f:
            while time.monotonic()<end:
                tick=time.monotonic()
                try:
                    r=snapshot(dev,reader);data=json.dumps(r,separators=(',',':')).encode()
                    if len(data)>1400:raise ValueError('feedback exceeds unfragmented wired packet budget')
                    sock.sendto(data,(peer,port));f.write(json.dumps({'mono':tick,'status':'sent','sample':r})+'\n')
                except (ValueError,OSError) as e:f.write(json.dumps({'mono':tick,'status':'hold','error':str(e)})+'\n')
                f.flush();time.sleep(max(0,min(.2-(time.monotonic()-tick),end-time.monotonic())))
    finally:sock.close()


def govern(cfg,seconds,trace,dry_run=False):
    from .linux import Shaper
    profile=cfg['native_radio_calibration'];reader=cfg['native_reader'];feedback=cfg['receiver_feedback']
    if profile.get('validated') is not True:raise ValueError('native radio calibration has not passed its validation gate')
    if os.uname().release!=profile['kernel_release']:raise ValueError('kernel outside calibrated scope')
    for name,digest in profile['module_srcversions'].items():
        if Path('/sys/module',name,'srcversion').read_text().strip()!=digest:raise ValueError('driver outside calibrated scope')
    if profile.get('payload_bytes')!=cfg['payload_bytes'] or cfg['payload_bytes']!=1048576:raise ValueError('payload outside W1 calibration')
    if hashlib.sha256(Path(reader).read_bytes()).hexdigest()!=profile['reader_sha256']:raise ValueError('native statistics reader changed')
    check_scope(profile,snapshot(cfg['dev'],reader))
    if dry_run:return {'mode':'adaptive','changed_system':False,'input_contract':'native-calibrated-receiver-feedback'}
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((feedback['bind'],feedback['port']));sock.setblocking(False)
    src=deque();recv=deque();cap=cfg['cap_packet_Bps'];end=time.monotonic()+seconds;shaper=Shaper(cfg)
    old_handler=signal.getsignal(signal.SIGTERM)
    def stop(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        shaper.install()
        with open(trace,'w',newline='') as f:
            columns=['monotonic_s','mode','status','cap_packet_Bps','beta','theta','relay_s','RX_coverage_ratio','mean_skb_bytes','qdisc_json','class_json','error'];w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
            while time.monotonic()<end:
                tick=time.monotonic();row={'monotonic_s':tick,'mode':'adaptive','status':'hold','cap_packet_Bps':cap,'error':''}
                try:
                    for _ in range(32):
                        try:data,addr=sock.recvfrom(2048)
                        except BlockingIOError:break
                        if addr[0]==feedback['peer']:recv.append((time.monotonic(),json.loads(data)))
                    src.append((time.monotonic(),snapshot(cfg['dev'],reader)))
                    for queue in (src,recv):
                        while len(queue)>2 and queue[1][0]<tick-3:queue.popleft()
                    if len(src)<2 or src[-1][0]-src[0][0]<2:raise ValueError('observation window warming up')
                    if len(recv)<2 or tick-recv[-1][0]>.6:raise ValueError('receiver feedback missing or stale')
                    e=estimate(profile,src[0][1],src[-1][1],recv[0][1],recv[-1][1]);cap=min(profile['cap_ceiling_skb_Bps'],max(1000,.7*cap+.3*e['cap_packet_Bps']));shaper.change(cap)
                    row.update(e,status='updated',cap_packet_Bps=cap)
                except (ValueError,KeyError,OSError,json.JSONDecodeError) as e:row['error']=str(e)
                row.update(qdisc_json=shaper.stats(),class_json=shaper.class_stats());w.writerow(row);f.flush();time.sleep(max(0,min(.2-(time.monotonic()-tick),end-time.monotonic())))
    finally:
        shaper.close();sock.close();signal.signal(signal.SIGTERM,old_handler)
    return {'mode':'adaptive','restored':True,'trace':str(trace),'input_contract':'native-calibrated-receiver-feedback'}
