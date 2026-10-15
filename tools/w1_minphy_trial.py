"""Standard receiver iperf only; new radio sampling program runs on sender4."""
import argparse,json,shlex,time,sys
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
from w1_sender_validation_finish import IPv6Control
BASE=ROOT/'runs/w1_20261014_ack_live'
class HybridControl(IPv6Control):
    def extra(self,host,command,data=None):
        if host=='4':command=shlex.join(['ssh','-o','IPQoS=none','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.4','csilab@192.168.50.2',command])
        return super().extra('5',command,data)
def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);p.add_argument('--rate-mbps',type=float,default=600);p.add_argument('--seconds',type=int,default=15);a=p.parse_args();out=BASE/a.tag;out.mkdir(exist_ok=False);c=HybridControl('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};folders={h:home+'/'+REMOTE+'/runs/'+BASE.name+'/'+a.tag for h,home in cam.homes.items()}
    for h in ['4','5']:
        r=c.python(h,"import json,subprocess;from pathlib import Path;Path("+repr(folders[h])+").mkdir(exist_ok=False);print(json.dumps({'link':subprocess.check_output(['iw','dev','wlp2s0','link'],text=True),'info':subprocess.check_output(['iw','dev','wlp2s0','info'],text=True),'qdisc':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0'])),'processes':subprocess.check_output(['ps','-eo','args'],text=True)}))")
        assert 'SSID: iptime5GAX1500\n' in r['link'] and all(q['kind']=='noqueue' for q in r['qdisc']);assert not any(x in r['processes'] for x in ['iperf3 -c','iperf3 -s','tools/traffic.py']);(out/('pre'+h+'.json')).write_text(json.dumps(r,indent=2))
    cam.write('4',cam.homes['4']+'/'+REMOTE+'/tools/w1_minphy_worker.py',(ROOT/'tools/w1_minphy_worker.py').read_bytes())
    if a.rate_mbps:cam.launch('5',['timeout','-k','2',str(a.seconds+15),'iperf3','-s','-1','-B','192.168.0.5','-p','55945','-J','-i','.2'],folders['5'],'server.json');time.sleep(.5)
    q=c.extra('4','cd '+shlex.quote(cam.homes['4']+'/'+REMOTE)+' && '+shlex.join(['sudo','-n','timeout','-k','3',str(a.seconds+15),'python3','-m','tools.w1_minphy_worker','--out',folders['4']+'/sample','--seconds',str(a.seconds),'--rate-mbps',str(a.rate_mbps)]));assert q.returncode==0,q.stderr
    time.sleep(2);cam.archive('4',folders['4']+'/sample',out/'4');cam.archive('5',folders['5'],out/'5');print('MINPHY SOURCE TRIAL '+a.tag,flush=True)
if __name__=='__main__':main()
