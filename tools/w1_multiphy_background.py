"""Finite same/other-AP competitor with original AP and buffer restoration."""
import argparse,json,shlex,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from deploy import ROOT,REMOTE,KEY,ssh
from w1_b2 import Control,SR2,OTHER
BASE=ROOT/'runs/w1_20261014_sender_multiphy'

def marker(h,action):
    user='csi2' if h=='12' else 'csi';folder='/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
    code="import json,time;from pathlib import Path;p=Path("+repr(folder)+");f=p/'command.pending';f.write_text(json.dumps({'id':time.time_ns(),'action':"+repr(action)+"}));f.replace(p/'command.json')"
    q=ssh(h,('sudo -n ' if h=='12' else '')+'python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())

def discover(bind,macs):
    def ping(ip):subprocess.run(['ping','-S',bind,'-n','1','-w','250',ip],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(ping,['192.168.0.'+str(i) for i in range(1,31)]))
    cmd="Get-NetNeighbor -InterfaceAlias 'Wi-Fi 2' -AddressFamily IPv4 | Select-Object IPAddress,LinkLayerAddress,State | ConvertTo-Json -Compress"
    rows=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',cmd]));rows=[rows] if isinstance(rows,dict) else rows
    result={}
    for h,mac in macs.items():
        hits=[r['IPAddress'] for r in rows if r['LinkLayerAddress'].lower().replace('-',':')==mac and r['State'] not in [0,1]]
        if len(hits)==1:result[h]=hits[0]
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['B2','C2'],required=True);p.add_argument('--tag',required=True);p.add_argument('--profile',default='frozen_profile.json');p.add_argument('--rate-mbps',type=float,default=0);a=p.parse_args()
    for x in [a.tag,a.profile]:
        if __import__('pathlib').Path(x).name!=x:p.error('single tag/profile')
    out=BASE/(a.tag+'_background');out.mkdir(exist_ok=False);c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);ips={'12':'192.168.0.3','10':'192.168.0.4'};homes={'12':'/home/csi2','10':'/home/csi'};old={};launch_time=None
    def peer(h,command,data=None):
        if a.kind=='B2':return ssh(h,command,data)
        return subprocess.run(['ssh','-b',c.bind,'-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.'+h,('csi2' if h=='12' else 'csi')+'@'+ips[h],command],input=data,capture_output=True,timeout=45)
    def remote(h,code):
        q=peer(h,'python3 -',code.encode())
        if q.returncode:raise RuntimeError(q.stderr.decode())
        return json.loads(q.stdout)
    folders={h:home+'/'+REMOTE+'/runs/'+BASE.name+'/'+out.name for h,home in homes.items()}
    def start(h,args,log):
        return remote(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folders[h])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(log)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    try:
        c.connect(SR2)
        if a.kind=='C2':
            q=ssh('12','sudo -n chown csi2:csi2 /home/csi2/'+REMOTE+'/runs/'+BASE.name);assert q.returncode==0
            for h in ['12','10']:marker(h,'ax')
            time.sleep(6);c.connect(OTHER)
            pre=json.loads((BASE/'preflight.json').read_text());macs={h:next(d['address'] for d in pre[h]['addresses'] if d['ifname']==('wlo1' if h=='12' else 'wlp2s0')) for h in ['12','10']}
            ips=discover(c.bind,macs)
            if len(ips)!=2:raise RuntimeError('could not uniquely discover both AX peers by recorded MAC: '+str(ips))
        inventory={}
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            inventory[h]=remote(h,"import subprocess,json;print(json.dumps({'link':subprocess.check_output(['iw','dev',"+repr(dev)+",'link'],text=True),'info':subprocess.check_output(['iw','dev',"+repr(dev)+",'info'],text=True),'MAC':subprocess.check_output(['cat','/sys/class/net/"+dev+"/address'],text=True).strip(),'processes':subprocess.check_output(['ps','-eo','args'],text=True)}))")
            assert 'SSID: '+(SR2 if a.kind=='B2' else OTHER)+'\n' in inventory[h]['link'] and 'channel 149 ' in inventory[h]['info']
            assert not any(x in inventory[h]['processes'] for x in ['iperf3 -c','iperf3 -s','tools/traffic.py'])
            old[h]=remote(h,"import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k])) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
            q=peer(h,'sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0,q.stderr
            code="import time,subprocess;time.sleep(100);subprocess.run("+repr(['sudo','-n','sysctl','-w']+[k+'='+str(v) for k,v in old[h].items()])+")";start(h,['timeout','-k','2','108','python3','-c',code],'buffer_guard.log')
        (out/'inventory.json').write_text(json.dumps({'kind':a.kind,'ips':ips,'nodes':inventory,'buffers_before':old},indent=2))
        start('10',['timeout','-k','2','82','iperf3','-s','-1','-B',ips['10'],'-p','55944','-J','-i','.2'],'server.json');time.sleep(.5)
        code="import subprocess,json,time;s=time.time();q=subprocess.run("+repr(['iperf3','-c',ips['10'],'-B',ips['12'],'-p','55944','-u','-b','300000000','-l','1400','-w','1048576','-t','70','-i','.2','-J'])+",capture_output=True,text=True,timeout=75);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_wall':s,'end_wall':time.time()}))"
        start('12',['timeout','-k','2','80','python3','-u','-c',code],'client.json');launch_time=time.monotonic()
        if a.kind=='B2':c.connect(OTHER)
        subprocess.run([sys.executable,str(ROOT/'tools/w1_sender_validate_run.py'),'--run',BASE.name,'--profile',a.profile,'--tag',a.tag,'--rate-mbps',str(a.rate_mbps),'--seconds','24','--fresh-association'],cwd=ROOT,check=True)
        time.sleep(max(0,launch_time+85-time.monotonic()))
        if a.kind=='B2':c.connect(SR2)
        for h,name in [('12','client.json'),('10','server.json')]:
            q=peer(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0,q.stderr;(out/(h+'_'+name)).write_bytes(q.stdout)
        data=json.loads((out/'12_client.json').read_text());assert data['rc']==0
        print(json.dumps({'kind':a.kind,'tag':a.tag,'competitor_rc':data['rc']}),flush=True)
    finally:
        if launch_time:time.sleep(max(0,min(55,launch_time+110-time.monotonic())))
        if a.kind=='B2':c.connect(SR2)
        rest={}
        for h,v in old.items():
            q=peer(h,'sudo -n sysctl -w '+shlex.join([k+'='+str(x) for k,x in v.items()]));rest[h]={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
        if a.kind=='C2':
            for h in ips:
                user='csi2' if h=='12' else 'csi';folder='/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
                code="import time,json;from pathlib import Path;p=Path("+repr(folder)+");f=p/'command.pending';f.write_text(json.dumps({'id':time.time_ns(),'action':'sr2'}));f.replace(p/'command.json')"
                q=peer(h,('sudo -n ' if h=='12' else '')+'python3 -',code.encode());rest[h]['return_marker_rc']=q.returncode
            time.sleep(6)
        (out/'restoration.json').write_text(json.dumps(rest,indent=2));c.connect(OTHER)
if __name__=='__main__':main()
