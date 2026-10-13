"""Bounded two-DDS adaptive functional check after held-out radio gates.

Wired feedback ends before govern to exercise stale-input holds. DDS remains
on Wi-Fi; this radio/control check makes no end-to-end latency claim.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics
import time
from deploy import ROOT, REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
import sys
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize


def main():
    base=ROOT/'runs/w1_20261013_radio_input_retry';out=base/'native_adaptive_smoke';out.mkdir(exist_ok=True)
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};cam.ips={'4':'192.168.0.4','5':'192.168.0.5'}
    aggregation=json.loads((base/'frozen_aggregation_coverage_profile.json').read_text());packet=json.loads((base/'frozen_radio_profile_v3_packet.json').read_text())
    proofs={}
    for folder in ['dds_confirmation','b2_aggregation_confirmation','c2_scheduled_radio']:
        path=base/folder/'aggregation_analysis.json'
        if not path.exists() and folder=='c2_scheduled_radio':
            candidates=list(base.glob('c2*/aggregation_analysis.json'));assert len(candidates)==1;cpath=candidates[0];path=cpath
        data=json.loads(path.read_text());rows=data['rows']
        if folder=='dds_confirmation':assert all(x['self_pass'] for x in rows)
        else:
            competing=[x for x in rows if 'error_fraction' in x and x['name']!='quiet']
            assert len(competing)==3 and all(abs(x['error_fraction'])<=.2 for x in competing)
        proofs[str(path.relative_to(base))]=hashlib.sha256(path.read_bytes()).hexdigest()
    C0=packet['C0_bps']/8
    identity={}
    for h in cam.homes:
        identity[h]=c.python(h,"import json,os;from pathlib import Path;print(json.dumps({'kernel_release':os.uname().release,'module_srcversions':{n:Path('/sys/module',n,'srcversion').read_text().strip() for n in ['mt76','mt792x_lib','mt7921e']}}))")
    assert identity['4']==identity['5']
    profile={k:aggregation[k] for k in ['BA_busy_s','RX_data_scale','RX_AMPDU_busy_s','idle_busy_fraction','AMPDU_byte_coverage_scale']}
    profile.update({k:packet[k] for k in ['O_up_s','O_down_s','station_link_header_bytes']})
    profile.update(identity['4'],validated=True,alpha=.9,cap_ceiling_skb_Bps=.9*C0,payload_bytes=1048576,AP='b0:38:6c:7d:f5:74',frequency_MHz=5745,width_MHz=80,reader_sha256='e64cf5ca976e8d9812978fa6b779443522d7a95416037feb10050cce809baa49',validation_sha256=proofs,scope='MT7921 AX149/80 1MiB operational calibration; no intrinsic PHY airtime claim')
    (out/'qualified_input_profile.json').write_text(json.dumps(profile,indent=2))
    for h,home in cam.homes.items():
        for path in ['rospacer/native_radio.py','rospacer/linux.py']:
            cam.write(h,home+'/'+REMOTE+'/'+path,(ROOT/path).read_bytes())
    manifest=json.loads((ROOT/'runs/w1_20261012_radio45/runtime/manifest.json').read_text())
    results=[]
    for rmw in ['fastdds','cyclonedds']:
        local=out/rmw;local.mkdir();folders={h:home+'/'+REMOTE+'/runs/'+base.name+'/'+out.name+'/'+rmw for h,home in cam.homes.items()}
        hz=.2*C0/1048576;count=math.ceil(hz*15);rtt=json.loads((base/'dds_confirmation/ping.json').read_text())['stdout'];import re
        cfg=synthesize(1048576,hz,1,C0,float(re.search(r'= [0-9.]+/([0-9.]+)/',rtt)[1])/1000,1)
        cfg.update(dev='wlp2s0',peers=[cam.ips['5']],cap_packet_Bps=.9*C0,native_radio_calibration=profile,native_reader=cam.homes['4']+'/'+REMOTE+'/tools/w1_etstats',receiver_feedback={'bind':'192.168.50.2','peer':'192.168.50.1','port':55910})
        old={};start=time.monotonic()
        print('START native adaptive '+rmw,flush=True)
        try:
            for h,home in cam.homes.items():
                old[h]=c.python(h,"import json,subprocess;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n','net.core.'+k])) for k in ['rmem_max','wmem_max']}))")
                xml=local/('profile'+h+'.xml');cam.profile(rmw,'static',h,cfg,xml);cam.write(h,folders[h]+'/middleware.xml',xml.read_bytes());cam.write(h,folders[h]+'/config.json',json.dumps(cfg,indent=2).encode())
                q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.rmem_max='+str(max(old[h]['rmem_max'],cfg['socket_rx_bytes'])),'net.core.wmem_max='+str(max(old[h]['wmem_max'],cfg['socket_tx_bytes']))]));assert q.returncode==0
                cam.launch(h,['sudo','-n','timeout','-k','2','48','python3','tools/w1_counter_worker.py','--mode','observe','--seconds','43','--interval','.2','--out',folders[h]+'/radio.json'],folders[h],'radio.log')
            feedback="from rospacer.native_radio import receiver_feedback;receiver_feedback('wlp2s0',"+repr(cam.homes['5']+'/'+REMOTE+'/tools/w1_etstats')+",'192.168.50.1','192.168.50.2',55910,33,"+repr(folders['5']+'/feedback.jsonl')+")"
            cam.launch('5',['sudo','-n','timeout','-k','2','37','python3','-c',feedback],folders['5'],'feedback.log')
            cam.launch('4',['sudo','-n','timeout','-k','2','48','python3','-m','rospacer','govern','--mode','adaptive','--config',folders['4']+'/config.json','--seconds','43','--trace',folders['4']+'/govern.csv'],folders['4'],'govern.log')
            env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=74 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
            def command(h,role):
                e=env+'export LD_LIBRARY_PATH='+cam.homes[h]+'/'+REMOTE+'/runtime_w1_45/'+rmw+':$LD_LIBRARY_PATH; '
                e+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+folders[h]+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+folders[h]+'/middleware.xml; ')
                args=['timeout','-k','2','37','python3','tools/traffic.py',role,'--seconds',str(15 if role=='pub' else 33),'--hz',str(hz),'--count',str(count),'--out',folders[h]+'/'+role+'.json']
                if role=='pub':args+=['--discovery-seconds','8','--drain-seconds','3','--continue-on-publish-error']
                return e+'cd '+cam.homes[h]+'/'+REMOTE+'; exec '+shlex.join(args)
            cam.launch('5',['bash','-c',command('5','sub')],folders['5'],'sub.log');time.sleep(.5);cam.launch('4',['bash','-c',command('4','pub')],folders['4'],'pub.log')
            while time.monotonic()-start<49:time.sleep(min(1,49-(time.monotonic()-start)))
            for h in cam.homes:cam.archive(h,folders[h],local/h)
            pub=json.loads((local/'4/pub.json').read_text());sub=json.loads((local/'5/sub.json').read_text());rows=list(csv.DictReader((local/'4/govern.csv').open()));updated=[r for r in rows if r['status']=='updated'];holds=[r for r in rows if r['error']=='receiver feedback missing or stale']
            intervals=[float(b['monotonic_s'])-float(a['monotonic_s']) for a,b in zip(updated,updated[1:])]
            library={}
            for h,role in [('4','pub'),('5','sub')]:
                actual=json.loads((local/h/(role+'.metadata.json')).read_text())['libraries'];expected=manifest[rmw]['manifest'];library[h]=bool(actual) and all('/runtime_w1_45/'+rmw+'/' in path and expected.get(Path(path).name)==sha for path,sha in actual.items())
            restored=c.python('4',"import json,subprocess;print(json.dumps({'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))}))")
            result={'rmw':rmw,'planned':count,'succeeded':pub['succeeded'],'received':sub['unique_received'],'runtime_valid':library,'updated':len(updated),'stale_feedback_holds':len(holds),'median_update_interval_s':statistics.median(intervals) if intervals else None,'maximum_cap_Mbps':max(float(r['cap_packet_Bps']) for r in rows)*8/1e6,'cap_ceiling_Mbps':.9*C0*8/1e6,'qdisc_restored':all(q['kind']=='noqueue' for q in restored['qdisc']),'latency_qualified':False,'scope':'clean radio functional check; wired feedback stop exercises hold; no adaptive superiority claim'}
            (local/'summary.json').write_text(json.dumps(result,indent=2));results.append(result);print(json.dumps(result),flush=True)
        finally:
            for h,v in old.items():
                q=c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.'+k+'='+str(val) for k,val in v.items()]));assert q.returncode==0
    (out/'summary.json').write_text(json.dumps({'trials':results,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['tools/w1_native_smoke.py','rospacer/native_radio.py','rospacer/linux.py']}},indent=2))


if __name__=='__main__':main()
