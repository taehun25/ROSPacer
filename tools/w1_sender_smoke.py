"""Two DDS sender-only shadow tests; receiver is DDS sink, not a controller input."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import statistics
import time
import sys
from deploy import ROOT, REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize


def main():
    p=argparse.ArgumentParser();p.add_argument('--rmw',choices=['fastdds','cyclonedds'],required=True);p.add_argument('--revision',default='v3');p.add_argument('--management4',default='192.168.50.2');p.add_argument('--run',default='w1_20261013_sender_only');p.add_argument('--profile',default='frozen_sender_profile_v2.json');a=p.parse_args()
    if Path(a.revision).name!=a.revision:p.error('single revision label required')
    if Path(a.run).name!=a.run or Path(a.profile).name!=a.profile:p.error('single run/profile')
    base=ROOT/'runs'/a.run;out=base/('dds_'+a.revision+'_'+a.rmw);out.mkdir(exist_ok=False)
    c=Control(a.management4,'192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};cam.ips={'4':'192.168.0.4','5':'192.168.0.5'}
    profile=json.loads((base/a.profile).read_text());C0=profile['capacity_reference']['C0_Bps']
    hz=.2*C0/1048576;count=math.ceil(hz*15);cfg=synthesize(1048576,hz,1,C0,.004,1)
    folders={h:home+'/'+REMOTE+'/runs/'+base.name+'/'+out.name for h,home in cam.homes.items()}
    cfg.update(dev='wlp2s0',peers=[cam.ips['5']],cap_packet_Bps=.9*C0,sender_radio_calibration=profile,native_reader=cam.homes['4']+'/'+REMOTE+'/tools/w1_etstats')
    cfg.update(sender_capture_file=folders['4']+'/sender.pcap',sender_snapshot_file=folders['4']+'/source_samples.jsonl')
    hashes={}
    for name in ['rospacer/sender_radio.py','rospacer/__main__.py','rospacer/linux.py']:
        hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        cam.write('4',cam.homes['4']+'/'+REMOTE+'/'+name,(ROOT/name).read_bytes())
    old={};restoration_errors=[]
    try:
        name='tools/w1_counter_worker.py';cam.write('5',cam.homes['5']+'/'+REMOTE+'/'+name,(ROOT/name).read_bytes())
        for h,home in cam.homes.items():
            before=c.python(h,"import json,subprocess;print(json.dumps({'interfaces':subprocess.check_output(['iw','dev'],text=True),'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0'])),'old':{k:int(subprocess.check_output(['sysctl','-n','net.core.'+k])) for k in ['rmem_max','wmem_max']}}))")
            assert 'rpmon' not in before['interfaces'] and 'w1mon' not in before['interfaces']
            assert all(q['kind']=='noqueue' for q in before['qdisc']);old[h]=before['old']
            xml=out/('profile'+h+'.xml');cam.profile(a.rmw,'static',h,cfg,xml);cam.write(h,folders[h]+'/middleware.xml',xml.read_bytes());cam.write(h,folders[h]+'/config.json',json.dumps(cfg,indent=2).encode())
            q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.rmem_max='+str(max(old[h]['rmem_max'],cfg['socket_rx_bytes'])),'net.core.wmem_max='+str(max(old[h]['wmem_max'],cfg['socket_tx_bytes']))]));assert q.returncode==0,q.stderr
        cam.launch('4',['sudo','-n','timeout','-k','6','44','python3','-m','rospacer','sender-observe','--config',folders['4']+'/config.json','--seconds','38','--trace',folders['4']+'/sender.csv'],folders['4'],'sender.log')
        cam.launch('5',['sudo','-n','timeout','-k','3','44','python3','tools/w1_counter_worker.py','--mode','observe','--seconds','38','--interval','.2','--out',folders['5']+'/reference_radio.json'],folders['5'],'reference.log')
        env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=74 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if a.rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
        def command(h,role):
            e=env+'export LD_LIBRARY_PATH='+cam.homes[h]+'/'+REMOTE+'/runtime_w1_45/'+a.rmw+':$LD_LIBRARY_PATH; '
            e+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+folders[h]+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if a.rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+folders[h]+'/middleware.xml; ')
            args=['timeout','-k','2','37','python3','tools/traffic.py',role,'--seconds',str(15 if role=='pub' else 33),'--hz',str(hz),'--count',str(count),'--out',folders[h]+'/'+role+'.json']
            if role=='pub':args+=['--discovery-seconds','8','--drain-seconds','3','--continue-on-publish-error']
            return e+'cd '+cam.homes[h]+'/'+REMOTE+'; exec '+shlex.join(args)
        cam.launch('5',['bash','-c',command('5','sub')],folders['5'],'sub.log');time.sleep(.5)
        cam.launch('4',['bash','-c',command('4','pub')],folders['4'],'pub.log')
        print('START sender-only DDS shadow '+a.rmw,flush=True);time.sleep(44)
        for h in cam.homes:cam.archive(h,folders[h],out/h)
        pub=json.loads((out/'4/pub.json').read_text());sub=json.loads((out/'5/sub.json').read_text());rows=list(csv.DictReader((out/'4/sender.csv').open()))
        estimated=[r for r in rows if r['status']=='estimated'];holds=Counter(r['error'] for r in rows if r['status']=='hold')
        steady=[r for r in rows if pub['measurement_started_ns']/1e9+4<=float(r['monotonic_s'])<=pub['measurement_ended_ns']/1e9-2]
        steady_estimated=[r for r in steady if r['status']=='estimated']
        final=c.python('4',"import json,subprocess;print(json.dumps({'interfaces':subprocess.check_output(['iw','dev'],text=True),'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))}))")
        manifest=json.loads((ROOT/'runs/w1_20261012_radio45/runtime/manifest.json').read_text())[a.rmw]['manifest']
        library={}
        for h,role in [('4','pub'),('5','sub')]:
            actual=json.loads((out/h/(role+'.metadata.json')).read_text())['libraries'];library[h]=bool(actual) and all('/runtime_w1_45/'+a.rmw+'/' in path and manifest.get(Path(path).name)==digest for path,digest in actual.items())
        result={'rmw':a.rmw,'planned':count,'published':pub['succeeded'],'received':sub['unique_received'],'runtime_valid':library,
                'sender_estimates':len(estimated),'holds':dict(holds),'beta_raw_range':[min(float(r['beta']) for r in estimated),max(float(r['beta']) for r in estimated)] if estimated else None,
                'downlink_Mbps':sorted({float(r['downlink_Mbps']) for r in estimated}),
                'monitor_removed':'rpmon' not in final['interfaces'],'qdisc_unchanged':all(q['kind']=='noqueue' for q in final['qdisc']),
                'receiver_feedback_used':False,'HTB_applied':False,'source_sha256':hashes,'latency_qualified':False,'purpose':'functional sender-only shadow; not adaptive performance qualification'}
        result.update(steady_windows=len(steady),steady_estimated=len(steady_estimated),success_fraction=len(steady_estimated)/len(steady) if steady else 0,steady_hold_reasons=dict(Counter(r['error'] for r in steady if r['status']=='hold')))
        (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    finally:
        for h,values in old.items():
            q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.'+k+'='+str(v) for k,v in values.items()]))
            if q.returncode:restoration_errors.append({'host':h,'error':q.stderr.decode()})
        (out/'restoration.json').write_text(json.dumps({'errors':restoration_errors,'baseline':old,'restored':not restoration_errors},indent=2))
        if restoration_errors:raise RuntimeError('sender smoke sysctl restoration failed: '+str(restoration_errors))


if __name__=='__main__':main()
