"""Check radio input on actual stock-runtime DDS1MiB Static bursts.

No E2E latency claims: current clocks are not qualified. QoS, actual library
closure, publish/receive counts and raw native counters are retained.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics
import time
from deploy import ROOT,REMOTE
from w1_b2 import Control,OTHER
from w1_ros45 import Campaign
import sys
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--seconds',type=int,default=15);p.add_argument('--label',default='dds_radio');a=p.parse_args()
    if not 10<=a.seconds<=20:p.error('bounded15s radio test')
    base=ROOT/'runs'/a.run;out=base/a.label;out.mkdir(parents=True,exist_ok=False)
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    # Current UDP capacity and a newly measured RTT; old metrics are untouched.
    C0=json.loads((base/'calibration/summary.json').read_text())['C0_receiver_median_bps']/8
    q=c.python('4',"import subprocess,json;q=subprocess.run(['ping','-n','-I','192.168.0.4','-c','100','-i','.05','-W','1','192.168.0.5'],capture_output=True,text=True,timeout=20);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}))")
    (out/'ping.json').write_text(json.dumps(q,indent=2));import re
    rtt=float(re.search(r'= [0-9.]+/([0-9.]+)/',q['stdout'])[1])/1000
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};cam.ips={'4':'192.168.0.4','5':'192.168.0.5'}
    manifest=json.loads((ROOT/'runs/w1_20261012_radio45/runtime/manifest.json').read_text())
    result=[]
    for rmw in ['fastdds','cyclonedds']:
        for rho in [.2,.5,.8]:
            name=f'{rmw}_rho{rho}';local=out/name;local.mkdir();folders={h:home+'/'+REMOTE+'/runs/'+a.run+'/'+a.label+'/'+name for h,home in cam.homes.items()}
            hz=rho*C0/1048576;count=math.ceil(hz*a.seconds);cfg=synthesize(1048576,hz,1,C0,rtt,1)
            print('DDS RADIO '+name,flush=True);old={}
            try:
                for h,home in cam.homes.items():
                    old[h]=c.python(h,"import json,subprocess;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n','net.core.'+k])) for k in ['rmem_max','wmem_max']}))")
                    profile=local/('profile'+h+'.xml');cam.profile(rmw,'static',h,cfg,profile);cam.write(h,folders[h]+'/middleware.xml',profile.read_bytes())
                    cam.write(h,folders[h]+'/config.json',json.dumps(cfg,indent=2).encode())
                    q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.rmem_max='+str(max(old[h]['rmem_max'],cfg['socket_rx_bytes'])),'net.core.wmem_max='+str(max(old[h]['wmem_max'],cfg['socket_tx_bytes']))]));assert q.returncode==0,q.stderr
                    cam.launch(h,['sudo','-n','timeout','-k','2','43','python3','tools/w1_counter_worker.py','--mode','observe','--seconds','38','--interval','.2','--out',folders[h]+'/radio.json'],folders[h],'radio.log')
                env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=74 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
                def command(h,role):
                    e=env+'export LD_LIBRARY_PATH='+cam.homes[h]+'/'+REMOTE+'/runtime_w1_45/'+rmw+':$LD_LIBRARY_PATH; '
                    e+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+folders[h]+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+folders[h]+'/middleware.xml; ')
                    args=['timeout','-k','2','37','python3','tools/traffic.py',role,'--seconds',str(a.seconds if role=='pub' else 33),'--hz',str(hz),'--count',str(count),'--out',folders[h]+'/'+role+'.json']
                    if role=='pub':args+=['--discovery-seconds','8','--drain-seconds','3','--continue-on-publish-error']
                    return e+'cd '+cam.homes[h]+'/'+REMOTE+'; exec '+shlex.join(args)
                cam.launch('5',['bash','-c',command('5','sub')],folders['5'],'sub.log');time.sleep(.5)
                cam.launch('4',['bash','-c',command('4','pub')],folders['4'],'pub.log')
                time.sleep(41)
                for h in cam.homes:cam.archive(h,folders[h],local/h)
                pub=json.loads((local/'4/pub.json').read_text());sub=json.loads((local/'5/sub.json').read_text());checks={}
                expected=manifest[rmw]['manifest']
                for h,role in [('4','pub'),('5','sub')]:
                    actual=json.loads((local/h/(role+'.metadata.json')).read_text())['libraries'];checks[h]=bool(actual) and all('/runtime_w1_45/'+rmw+'/' in path and expected.get(Path(path).name)==digest for path,digest in actual.items())
                s={'name':name,'rho_requested':rho,'requested_hz':hz,'planned':count,'succeeded':pub['succeeded'],'received':sub['unique_received'],'publisher_error':pub['error'],'subscriber_error':sub['error'],'runtime_valid':checks,'config':cfg,'latency_qualified':False}
                (local/'summary.json').write_text(json.dumps(s,indent=2));result.append(s);(out/'progress.json').write_text(json.dumps(result,indent=2));print(json.dumps(s),flush=True)
            finally:
                for h,v in old.items():
                    q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.'+k+'='+str(val) for k,val in v.items()]));assert q.returncode==0,q.stderr
    (out/'summary.json').write_text(json.dumps({'trials':result,'C0_bps':C0*8,'rtt_s':rtt,'normal_adaptive_qualified':False,'scope':'actual DDS Static radio self-load; no latency comparison'},indent=2))


if __name__=='__main__':main()
