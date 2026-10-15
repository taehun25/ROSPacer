"""One finite live sender shadow trial; receiver statistics are offline only."""
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize

BASE=ROOT/'runs/w1_20261013_sender_validation'
def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);p.add_argument('--rate-mbps',type=float,required=True);p.add_argument('--seconds',type=int,default=24);p.add_argument('--no-monitor',action='store_true');p.add_argument('--run',default=BASE.name);p.add_argument('--profile',default='frozen_profile.json');p.add_argument('--fresh-association',action='store_true');a=p.parse_args()
    if Path(a.tag).name!=a.tag or not 12<=a.seconds<=31 or not 0<=a.rate_mbps<=350:p.error('bounded tag/rate/duration required (reference worker <=40s)')
    if Path(a.run).name!=a.run or Path(a.profile).name!=a.profile:p.error('single run/profile name required')
    base=ROOT/'runs'/a.run
    out=base/a.tag;out.mkdir(exist_ok=False);c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    homes={'4':'/home/csilab','5':'/home/csi'};folders={h:home+'/'+REMOTE+'/runs/'+base.name+'/'+a.tag for h,home in homes.items()}
    cam=object.__new__(Campaign);cam.c=c;cam.homes=homes
    profile=json.loads((base/a.profile).read_text());c0=profile['capacity_reference']['C0_Bps']
    cfg=synthesize(1048576,.2*c0/1048576,1,c0,.004,1)
    cfg.update(dev='wlp2s0',peers=['192.168.0.5'],cap_packet_Bps=.9*c0,sender_radio_calibration=profile,native_reader=homes['4']+'/'+REMOTE+'/tools/w1_etstats',
               sender_capture_file=folders['4']+'/sender.pcap',sender_snapshot_file=folders['4']+'/source_samples.jsonl')
    inventory={}
    for h in homes:
        inventory[h]=c.python(h,"import subprocess,json;print(json.dumps({'host':subprocess.check_output(['hostname'],text=True).strip(),'link':subprocess.check_output(['iw','dev','wlp2s0','link'],text=True),'interfaces':subprocess.check_output(['iw','dev'],text=True),'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0'])),'processes':subprocess.check_output(['ps','-eo','pid,args'],text=True)}))")
        r=inventory[h];assert 'SSID: iptime5GAX1500\n' in r['link'] and 'channel 149 ' in r['interfaces']
        assert 'type monitor' not in r['interfaces'] and all(q['kind']=='noqueue' for q in r['qdisc'])
        assert not any(x in r['processes'] for x in ['iperf3 -c','iperf3 -s','tools/w1_counter_worker.py',' -m rospacer sender-observe','tools/traffic.py'])
        c.python(h,"import json;from pathlib import Path;Path("+repr(folders[h])+").mkdir(parents=True,exist_ok=False);print('{}')")
    fresh=None
    if a.fresh_association:
        q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0,q.stderr
        fresh={'rc':q.returncode,'out':q.stdout.decode(),'purpose':'explicit idle pre-run reset, not exit recovery; no DDS trial active'}
        q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0
    hashes={}
    for name in ['rospacer/sender_radio.py','rospacer/__main__.py','rospacer/linux.py','tools/w1_counter_worker.py']:
        data=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(data).hexdigest()
        for h in (['4','5'] if name.startswith('tools/') else ['4']):cam.write(h,homes[h]+'/'+REMOTE+'/'+name,data)
    cam.write('4',folders['4']+'/config.json',json.dumps(cfg,indent=2).encode())
    duration=a.seconds+9
    launched=time.monotonic()
    if not a.no_monitor:
        cam.launch('4',['sudo','-n','timeout','-k','5',str(duration+5),'python3','-m','rospacer','sender-observe','--config',folders['4']+'/config.json','--seconds',str(duration),'--trace',folders['4']+'/sender.csv'],folders['4'],'sender.log')
    else:
        cam.launch('4',['sudo','-n','timeout','-k','3',str(duration+5),'python3','tools/w1_counter_worker.py','--mode','observe','--seconds',str(duration),'--interval','.2','--out',folders['4']+'/radio.json'],folders['4'],'source.log')
    cam.launch('5',['sudo','-n','timeout','-k','3',str(duration+5),'python3','tools/w1_counter_worker.py','--mode','observe','--seconds',str(duration),'--interval','.2','--out',folders['5']+'/reference_radio.json'],folders['5'],'reference.log')
    cam.launch('5',['timeout','-k','2',str(a.seconds+15),'iperf3','-s','-1','-B','192.168.0.5','-p','55940','-J','-i','.2'],folders['5'],'server.json')
    time.sleep(3)
    args=['iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55940','--connect-timeout','2000','-u','-b',str(round(a.rate_mbps*1e6)),'-l','1400','-w','1048576','-t',str(a.seconds),'-i','.2','-J']
    client=c.python('4',"import subprocess,json,time;start=time.monotonic();wall=time.time()\ntry:\n q=subprocess.run("+repr(args)+",capture_output=True,text=True,timeout="+str(a.seconds+7)+");r={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nexcept subprocess.TimeoutExpired:\n r={'rc':124,'stdout':'','stderr':'main iperf timeout'}\nr.update(start_monotonic=start,end_monotonic=time.monotonic(),start_wall=wall,end_wall=time.time());print(json.dumps(r))")
    (out/'client.json').write_text(json.dumps(client,indent=2))
    # Even a failed TCP startup must not trigger lifecycle checks during capture.
    time.sleep(max(0,launched+duration+12-time.monotonic()))
    for h in homes:cam.archive(h,folders[h],out/h)
    lifecycle=c.python('4',"import subprocess,json;r={}\nfor k,args in {'interfaces':['iw','dev'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'power':['iw','dev','wlp2s0','get','power_save'],'ping':['ping','-I','wlp2s0','-c','2','-W','1','192.168.0.5']}.items():\n q=subprocess.run(args,capture_output=True,text=True,timeout=5);r[k]={'rc':q.returncode,'out':q.stdout,'err':q.stderr}\nprint(json.dumps(r))")
    q=c.extra('5',shlex.join(['timeout','-k','1','8','ssh','-o','BatchMode=yes','-o','ConnectTimeout=3','-o','HostKeyAlias=192.168.0.4','csilab@192.168.0.4','hostname']))
    lifecycle['ordinary_wifi_ssh']={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
    healthy=lifecycle['ping']['rc']==0 and q.returncode==0 and 'type monitor' not in lifecycle['interfaces']['out']
    lifecycle['healthy_without_reconnect']=healthy
    if not healthy:
        q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');lifecycle['reconnect']={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
        q=c.extra('5',shlex.join(['timeout','-k','1','8','ssh','-o','BatchMode=yes','-o','ConnectTimeout=3','-o','HostKeyAlias=192.168.0.4','csilab@192.168.0.4','hostname']));lifecycle['recovered_wifi_ssh']=q.returncode==0
    (out/'lifecycle.json').write_text(json.dumps(lifecycle,indent=2));(out/'manifest.json').write_text(json.dumps({'source_sha256':hashes,'profile_sha256':hashlib.sha256((base/a.profile).read_bytes()).hexdigest(),'rate_requested_Mbps':a.rate_mbps,'seconds':a.seconds,'monitor':not a.no_monitor,'receiver_feedback':False,'HTB':False,'inventory':inventory,'fresh_association_before_run':fresh},indent=2))
    print(json.dumps({'tag':a.tag,'client_rc':client['rc'],'lifecycle_without_reconnect':healthy,'recovered':lifecycle.get('recovered_wifi_ssh',healthy)}),flush=True)
if __name__=='__main__':main()
