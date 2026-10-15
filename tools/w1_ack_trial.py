"""Finite sender-managed-interface RTPS observation and offline receiver check."""
import argparse,hashlib,json,math,shlex,subprocess,time,sys
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize
BASE=ROOT/'runs/w1_20261014_ack_live'
def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);p.add_argument('--rmw',choices=['fastdds','cyclonedds'],required=True);p.add_argument('--hz',type=float,default=4);p.add_argument('--mask',action='store_true');p.add_argument('--mode',choices=['fixed','ack'],default='ack');a=p.parse_args()
    if not a.tag.replace('_','').isalnum() or not 1<=a.hz<=30:p.error('bounded tag/rate')
    out=BASE/a.tag;out.mkdir(exist_ok=False);c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};cam.ips={'4':'192.168.0.4','5':'192.168.0.5'}
    C0=339.7268909014242*1e6/8;cfg=synthesize(1048576,a.hz,1,C0,.018545,1);cfg.update(dev='wlp2s0',peers=['192.168.0.5'])
    folders={h:home+'/'+REMOTE+'/runs/'+BASE.name+'/'+a.tag for h,home in cam.homes.items()};old={}
    
    for name in ['rospacer/sender_protocol.py','rospacer/sender_ack_live.py','rospacer/linux.py']:
        cam.write('4',cam.homes['4']+'/'+REMOTE+'/'+name,(ROOT/name).read_bytes())
    source_hash={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['rospacer/sender_protocol.py','rospacer/sender_ack_live.py','rospacer/linux.py']}
    cfg.update(experimental_ack_trial=True,ack_ceiling_packet_Bps=.9*C0,cap_packet_Bps=.9*C0)
    for h in cam.homes:
        pre=c.python(h,"import json,subprocess;r={'interfaces':subprocess.check_output(['iw','dev'],text=True),'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0'])),'processes':subprocess.check_output(['ps','-eo','args'],text=True)};print(json.dumps(r))")
        assert 'type monitor' not in pre['interfaces'] and all(q['kind']=='noqueue' for q in pre['qdisc'])
        assert not any(x in pre['processes'] for x in ['tools/traffic.py','iperf3 -c','iperf3 -s',' -m rospacer.sender_protocol',' -m rospacer.sender_ack_live --config'])
        c.python(h,"import json;from pathlib import Path;Path("+repr(folders[h])+").mkdir(parents=True,exist_ok=False);print('{}')")
        xml=out/('profile'+h+'.xml');cam.profile(a.rmw,'static',h,cfg,xml);cam.write(h,folders[h]+'/middleware.xml',xml.read_bytes());cam.write(h,folders[h]+'/config.json',json.dumps(cfg,indent=2).encode())
    q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0
    q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0
    observer=['sudo','-n','timeout','-k','3','75','python3','-m','rospacer.sender_ack_live','--config',folders['4']+'/config.json','--source','192.168.0.4','--peer','192.168.0.5','--out',folders['4']+'/live','--seconds','65','--mode',a.mode]
    if a.mask:observer+=['--mask-start','12','--mask-seconds','5']
    cam.launch('4',observer,folders['4'],'observer.log')
    env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=75 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if a.rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
    def command(h,role):
        e=env+'export LD_LIBRARY_PATH='+cam.homes[h]+'/'+REMOTE+'/runtime_w1_45/'+a.rmw+':$LD_LIBRARY_PATH; '
        e+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+folders[h]+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if a.rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+folders[h]+'/middleware.xml; ')
        args=['timeout','-k','2','64','python3','tools/traffic.py',role,'--seconds',str(30 if role=='pub' else 60),'--hz',str(a.hz),'--count',str(math.ceil(a.hz*30)),'--out',folders[h]+'/'+role+'.json']
        if role=='pub':args+=['--discovery-seconds','8','--drain-seconds','5','--continue-on-publish-error']
        return e+'cd '+cam.homes[h]+'/'+REMOTE+'; exec '+shlex.join(args)
    cam.launch('5',['bash','-c',command('5','sub')],folders['5'],'sub.log');time.sleep(.7);cam.launch('4',['bash','-c',command('4','pub')],folders['4'],'pub.log')
    (out/'manifest.json').write_text(json.dumps({'rmw':a.rmw,'hz':a.hz,'seconds':30,'payload_bytes':1048576,'phase':'held-out observation trial','mask':a.mask,'source_sha256':source_hash,'HTB_applied':True,'control_mode':a.mode,'receiver_statistics_feedback':False,'natural_ACKNACK_used':True,'ACK_scope':'protocol-only not wireless capacity','wireless_airtime_reconstructed':False,'fresh_association_before_run':True},indent=2))
    print('START live ACK trial '+a.tag,flush=True);time.sleep(72)
    for h in cam.homes:cam.archive(h,folders[h],out/h)
    cam.archive('4',folders['4']+'/live',out/'4/live');cam.archive('4',folders['4']+'/live/protocol',out/'4/protocol')
    live=json.loads((out/'4/live/summary.json').read_text());assert live['restored'] and live['error'] is None;assert live['HTB_applied'];o=json.loads((out/'4/protocol/summary.json').read_text());pub=json.loads((out/'4/pub.json').read_text());sub=json.loads((out/'5/sub.json').read_text())
    manifest=json.loads((ROOT/'runs/w1_20261012_radio45/runtime/manifest.json').read_text())[a.rmw]['manifest'];libs={}
    for h,role in [('4','pub'),('5','sub')]:
        actual=json.loads((out/h/(role+'.metadata.json')).read_text())['libraries'];libs[h]=bool(actual) and all('/runtime_w1_45/'+a.rmw+'/' in path and manifest.get(__import__('pathlib').Path(path).name)==digest for path,digest in actual.items())
    q=c.extra('5','timeout -k 1 7 ssh -o BatchMode=yes -o ConnectTimeout=3 -o HostKeyAlias=192.168.0.4 csilab@192.168.0.4 hostname')
    r={'tag':a.tag,'rmw':a.rmw,'planned':math.ceil(a.hz*30),'published':pub['succeeded'],'received':sub['unique_received'],'observed':o['observed_samples'],'confirmed':o['confirmed_samples'],'capture_drops':o['capture_drops'],'scope_error':o['scope_error'],'observer_errors':o['errors'],'masked_ack_events':o['masked_ack_events'],'wifi_exit_ssh':q.returncode==0,'runtime_valid':libs,'HTB_changes':live['HTB_changes'],'qdisc_restored':live['restored'],
       'observation_matches_receiver':o['confirmed_samples']==sub['unique_received'] and o['observed_samples']==pub['succeeded'],'HTB_applied':True,'control_mode':a.mode,'receiver_statistics_feedback':False}
    (out/'summary.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
if __name__=='__main__':main()
