"""Finite two-AP competition diagnosis for the sender-only frozen profile."""
import json
import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER


def remote(host,code):
    q=ssh(host,'python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return json.loads(q.stdout)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='w1_20261013_sender_only');p.add_argument('--label',default='validationB2_100');p.add_argument('--fcsfail',action='store_true');p.add_argument('--ap-control',action='store_true');p.add_argument('--origin',choices=['sender','pc'],default='sender');p.add_argument('--management4',choices=['192.168.50.2','192.168.0.4'],default='192.168.50.2');a=p.parse_args()
    if Path(a.run).name!=a.run or Path(a.label).name!=a.label:p.error('single run/label required')
    out=ROOT/'runs'/a.run/(a.label+'_background');out.mkdir(parents=True,exist_ok=False)
    c=Control(a.management4,'192.168.0.5','Wi-Fi 2',out)
    homes={'12':'/home/csi2','10':'/home/csi'};folders={h:home+'/'+REMOTE+'/runs/'+a.run+'/'+out.name for h,home in homes.items()}
    launched=None
    try:
        c.connect(SR2)
        inventory={}
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            inventory[h]=remote(h,"import subprocess,json;r={}\nfor k,args in {'link':['iw','dev',"+repr(dev)+",'link'],'info':['iw','dev',"+repr(dev)+",'info'],'processes':['ps','-eo','pid,args'],'hostname':['hostname']}.items():\n q=subprocess.run(args,capture_output=True,text=True,timeout=6);r[k]=q.stdout\nprint(json.dumps(r))")
            assert 'SSID: '+SR2+'\n' in inventory[h]['link']
            assert 'channel 149 ' in inventory[h]['info'] and 'width: 80 MHz' in inventory[h]['info']
            assert not any(s in inventory[h]['processes'] for s in ['iperf3 -c','iperf3 -s','tools/traffic.py'])
        (out/'inventory.json').write_text(json.dumps(inventory,indent=2))
        def start(h,args,name):
            return remote(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folders[h])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(name)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
        start('10',['timeout','-k','2','58','iperf3','-s','-1','-B','192.168.0.4','-p','55922','-J'],'server.json')
        time.sleep(.5)
        worker="import subprocess,json,time;start=time.time();q=subprocess.run(['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55922','-u','-b','300000000','-l','1400','-t','48','-J'],capture_output=True,text=True,timeout=54);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_wall':start,'end_wall':time.time()}))"
        start('12',['timeout','-k','2','57','python3','-u','-c',worker],'client.json');launched=time.monotonic()
        c.connect(OTHER)
        subprocess.run([sys.executable,str(ROOT/'tools/w1_sender_probe.py'),'--run',a.run,'--label',a.label,'--rate-mbps','100','--management4',a.management4,'--awake','--origin',a.origin]+(['--fcsfail'] if a.fcsfail else [])+(['--ap-control'] if a.ap_control else []),cwd=ROOT,check=True)
        remaining=launched+55-time.monotonic()
        if remaining>0:time.sleep(min(remaining,55))
        c.connect(SR2)
        for h,name in [('12','client.json'),('10','server.json')]:
            q=ssh(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0,q.stderr
            (out/(h+'_'+name)).write_bytes(q.stdout)
        data=json.loads((out/'12_client.json').read_text());assert data['rc']==0
        print(json.dumps({'background_rc':data['rc'],'scope':'continuous requested300Mbps 12→10 on SR2; main4→5 on AX; shared149/80; beta diagnosis only'}),flush=True)
    finally:c.connect(OTHER)


if __name__=='__main__':main()
