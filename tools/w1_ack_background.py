"""Finite same/other-AP competitor with original AP and buffer restoration."""
import argparse,json,shlex,subprocess,sys,time,os
from concurrent.futures import ThreadPoolExecutor
from deploy import ROOT,REMOTE,KEY,ssh
from w1_b2 import Control,SR2,OTHER
BASE=ROOT/'runs/w1_20261014_ack_live'

def connect_stable(c,ssid):
    c.connect(ssid);time.sleep(2)
    values=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',"Get-NetIPAddress -InterfaceAlias 'Wi-Fi 2' -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress"]))
    values=[values] if isinstance(values,str) else values
    valid=[v for v in values if v.startswith('192.168.0.')]
    if len(valid)!=1:raise RuntimeError('stable controller IPv4 unavailable')
    c.bind=valid[0];os.environ['ROSPACER_SSH_BIND']=c.bind

def marker(h,action):
    user='csi2' if h=='12' else 'csi';folder='/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
    code="import json,time;from pathlib import Path;p=Path("+repr(folder)+");f=p/'command.pending';f.write_text(json.dumps({'id':time.time_ns(),'action':"+repr(action)+"}));f.replace(p/'command.json')"
    q=sr2_peer(h,('sudo -n ' if h=='12' else '')+'python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())

def sr2_peer(h,command,data=None):
    pre=json.loads((BASE/'preflight1210.json').read_text());dev='wlo1' if h=='12' else 'wlp2s0'
    addresses=json.loads(pre[h]['data']['addresses']['stdout']);iface=next(x for x in addresses if x['ifname']==dev);ll=next(x['local'] for x in iface['addr_info'] if x['family']=='inet6' and x['scope']=='link')
    index=subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-NetAdapter -Name 'Wi-Fi 2').ifIndex"],text=True).strip()
    return subprocess.run(['ssh','-6','-i',KEY,'-o','IPQoS=none','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.'+h,('csi2' if h=='12' else 'csi')+'@'+ll+'%'+index,command],input=data,capture_output=True,timeout=45)

def discover(bind,macs):
    def ping(ip):subprocess.run(['ping','-S',bind,'-n','1','-w','250',ip],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(ping,['192.168.0.'+str(i) for i in range(1,31)]))
    cmd="Get-NetNeighbor -InterfaceAlias 'Wi-Fi 2' -AddressFamily IPv4 | Select-Object IPAddress,LinkLayerAddress,State | ConvertTo-Json -Compress"
    rows=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',cmd]));rows=[rows] if isinstance(rows,dict) else rows
    result={}
    for h,mac in macs.items():
        hits=[r['IPAddress'] for r in rows if r['LinkLayerAddress'].lower().replace('-',':')==mac and r['State'] in [5,6,'Reachable','Permanent']]
        if len(hits)==1:result[h]=hits[0]
    return result

def main():
    global BASE
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['B2','C2'],required=True);p.add_argument('--tag',required=True);p.add_argument('--rmw',choices=['fastdds','cyclonedds'],required=True);p.add_argument('--mode',choices=['fixed','ack'],required=True);p.add_argument('--minphy',action='store_true');p.add_argument('--minphy-ros',action='store_true');p.add_argument('--integrated',action='store_true');p.add_argument('--integrated-smoke',action='store_true');p.add_argument('--integrated-both',action='store_true');p.add_argument('--background-seconds',type=int,choices=range(30,601),default=90);p.add_argument('--run');a=p.parse_args()
    if a.run:
        if not a.run.startswith('w1_') or __import__('pathlib').Path(a.run).name!=a.run:p.error('owned W1 run name required')
        BASE=ROOT/'runs'/a.run
    for x in [a.tag]:
        if __import__('pathlib').Path(x).name!=x:p.error('single tag/profile')
    out=BASE/(a.tag+'_background');out.mkdir(exist_ok=False);c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);ips={'12':'192.168.0.3','10':'192.168.0.4'};homes={'12':'/home/csi2','10':'/home/csi'};old={};launch_time=None
    def peer(h,command,data=None):
        if a.kind=='B2':return sr2_peer(h,command,data)
        return subprocess.run(['ssh','-b',c.bind,'-i',KEY,'-o','IPQoS=none','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.'+h,('csi2' if h=='12' else 'csi')+'@'+ips[h],command],input=data,capture_output=True,timeout=45)
    def remote(h,code):
        q=peer(h,'python3 -',code.encode())
        if q.returncode:raise RuntimeError(q.stderr.decode())
        return json.loads(q.stdout)
    folders={h:home+'/'+REMOTE+'/runs/'+BASE.name+'/'+out.name for h,home in homes.items()}
    # The manually started root AP helper may own its parent. Traffic logs need
    # no privilege; keep peer10's logs in a fresh sibling under its user runs.
    folders['10']=homes['10']+'/'+REMOTE+'/runs/'+BASE.name+'_background10_logs/'+out.name
    def start(h,args,log):
        return remote(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folders[h])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(log)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    try:
        connect_stable(c,SR2)
        for host in ['12','10']:
            ready=sr2_peer(host,'hostname')
            if ready.returncode:time.sleep(2);ready=sr2_peer(host,'hostname')
            assert ready.returncode==0,ready.stderr
        if a.kind=='C2':
            for h in ['12','10']:marker(h,'ax')
            time.sleep(6);connect_stable(c,OTHER)
            pre=json.loads((BASE/'preflight1210.json').read_text());macs={h:next(d['address'] for d in json.loads(pre[h]['data']['addresses']['stdout']) if d['ifname']==('wlo1' if h=='12' else 'wlp2s0')) for h in ['12','10']}
            ips=discover(c.bind,macs)
            for _ in range(3):
                if len(ips)==2:break
                time.sleep(3);ips=discover(c.bind,macs)
            # Ping may not answer within250ms just after an AP switch. Verify
            # known DHCP candidates by SSH host key AND actual MAC/SSID.
            for h,candidate in [('12','192.168.0.12'),('10','192.168.0.10')]:
                if h in ips:continue
                code="import json,subprocess;from pathlib import Path;print(json.dumps({'MAC':Path('/sys/class/net/"+('wlo1' if h=='12' else 'wlp2s0')+"/address').read_text().strip(),'link':subprocess.check_output(['iw','dev',"+repr('wlo1' if h=='12' else 'wlp2s0')+",'link'],text=True)}))"
                q=subprocess.run(['ssh','-b',c.bind,'-i',KEY,'-o','IPQoS=none','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.'+h,('csi2' if h=='12' else 'csi')+'@'+candidate,'python3 -'],input=code.encode(),capture_output=True,timeout=15)
                if q.returncode==0:
                    identity=json.loads(q.stdout)
                    if identity['MAC']==macs[h] and 'SSID: '+OTHER+'\n' in identity['link']:ips[h]=candidate
            if len(ips)!=2:raise RuntimeError('could not uniquely discover both AX peers by recorded MAC: '+str(ips))
        inventory={}
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            inventory[h]=remote(h,"import subprocess,json;print(json.dumps({'link':subprocess.check_output(['iw','dev',"+repr(dev)+",'link'],text=True),'info':subprocess.check_output(['iw','dev',"+repr(dev)+",'info'],text=True),'MAC':subprocess.check_output(['cat','/sys/class/net/"+dev+"/address'],text=True).strip(),'processes':subprocess.check_output(['ps','-eo','args'],text=True)}))")
            assert 'SSID: '+(SR2 if a.kind=='B2' else OTHER)+'\n' in inventory[h]['link'] and 'channel 149 ' in inventory[h]['info']
            assert not any(x in inventory[h]['processes'] for x in ['iperf3 -c','iperf3 -s','tools/traffic.py'])
            old[h]=remote(h,"import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k])) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
            q=peer(h,'sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0,q.stderr
            code="import time,subprocess;time.sleep("+str(a.background_seconds+30)+");subprocess.run("+repr(['sudo','-n','sysctl','-w']+[k+'='+str(v) for k,v in old[h].items()])+")";start(h,['timeout','-k','2',str(a.background_seconds+38),'python3','-c',code],'buffer_guard.log')
        (out/'inventory.json').write_text(json.dumps({'kind':a.kind,'ips':ips,'nodes':inventory,'buffers_before':old},indent=2))
        def udp_counter(h):
            code="import json;from pathlib import Path;lines=Path('/proc/net/snmp').read_text().splitlines();pairs=[(a.split()[1:],b.split()[1:]) for a,b in zip(lines[::2],lines[1::2]) if a.startswith('Udp:')];print(json.dumps(dict(zip(pairs[0][0],map(int,pairs[0][1])))))"
            for attempt in range(3):
                q=peer(h,'python3 -',code.encode())
                if q.returncode==0:return json.loads(q.stdout)
                if attempt<2:time.sleep(2)
            raise RuntimeError('Readonly UDP startup counter failed: '+q.stderr.decode())
        counter_before={h:udp_counter(h) for h in ['12','10']}
        server_pid=start('10',['timeout','-k','2',str(a.background_seconds+15),'iperf3','-s','-1','-B',ips['10'],'-p','55944','-J','-i','.2'],'server.json');time.sleep(.5)
        code="import subprocess,json,time;s=time.time();q=subprocess.run("+repr(['iperf3','-c',ips['10'],'-B',ips['12'],'-p','55944','-u','-b','300000000','-l','1400','-w','1048576','-t',str(a.background_seconds),'-i','.2','-J'])+",capture_output=True,text=True,timeout="+str(a.background_seconds+5)+");print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_wall':s,'end_wall':time.time()}))"
        client_pid=start('12',['timeout','-k','2',str(a.background_seconds+10),'python3','-u','-c',code],'client.json');launch_time=time.monotonic()
        time.sleep(4);counter_after={h:udp_counter(h) for h in ['12','10']}
        proof={'before':counter_before,'after':counter_after,'source_out_delta':counter_after['12']['OutDatagrams']-counter_before['12']['OutDatagrams'],'receiver_in_delta':counter_after['10']['InDatagrams']-counter_before['10']['InDatagrams'],'client_pid':client_pid,'server_pid':server_pid}
        (out/'startup_udp_proof.json').write_text(json.dumps(proof,indent=2))
        if min(proof['source_out_delta'],proof['receiver_in_delta'])<1000:
            for h,owned in [('12',client_pid),('10',server_pid)]:
                code="import os,signal,json;from pathlib import Path;p="+str(owned['pid'])+";f=Path('/proc')/str(p)/'cmdline'\nif f.exists():\n s=f.read_bytes().decode(errors='replace');assert 'iperf3' in s and os.getpgid(p)==p;os.killpg(p,signal.SIGTERM)\nprint('{}')"
                remote(h,code)
            raise RuntimeError('Competitor UDP did not start; DDS trial not dispatched')
        if a.kind=='B2':connect_stable(c,OTHER)
        command=[sys.executable,str(ROOT/'tools/w1_minphy_trial.py'),'--tag',a.tag,'--rate-mbps','600','--seconds','15'] if a.minphy else [sys.executable,str(ROOT/'tools/w1_ack_trial.py'),'--tag',a.tag,'--rmw',a.rmw,'--mode',a.mode,'--hz','30']
        if a.minphy_ros:command=[sys.executable,str(ROOT/'tools/w1_minphy_ros_trial.py'),'--tag',a.tag,'--rmw',a.rmw,'--mode','ack','--hz','30']
        if a.integrated:command=[sys.executable,str(ROOT/'tools/w1_sender_integrated.py'),'launch','validate',a.tag,a.kind]
        if a.integrated_smoke:command=[sys.executable,str(ROOT/'tools/w1_sender_integrated.py'),'smoke',a.tag,a.rmw,a.kind]
        if a.integrated_both:command=[sys.executable,str(ROOT/'tools/w1_sender_integrated.py'),'smoke',a.tag,'both',a.kind]
        subprocess.run(command,cwd=ROOT,check=True)
        time.sleep(max(0,launch_time+a.background_seconds+20-time.monotonic()))
        if a.kind=='B2':connect_stable(c,SR2)
        for h,name in [('12','client.json'),('10','server.json')]:
            q=peer(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0,q.stderr;(out/(h+'_'+name)).write_bytes(q.stdout)
        data=json.loads((out/'12_client.json').read_text());assert data['rc']==0
        print(json.dumps({'kind':a.kind,'tag':a.tag,'competitor_rc':data['rc']}),flush=True)
    finally:
        if launch_time:time.sleep(max(0,min(55,launch_time+a.background_seconds+40-time.monotonic())))
        if a.kind=='B2':connect_stable(c,SR2)
        rest={}
        for h,v in old.items():
            q=peer(h,'sudo -n sysctl -w '+shlex.join([k+'='+str(x) for k,x in v.items()]));rest[h]={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
        if a.kind=='C2':
            for h in ips:
                user='csi2' if h=='12' else 'csi';folder='/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
                code="import time,json;from pathlib import Path;p=Path("+repr(folder)+");f=p/'command.pending';f.write_text(json.dumps({'id':time.time_ns(),'action':'sr2'}));f.replace(p/'command.json')"
                q=peer(h,('sudo -n ' if h=='12' else '')+'python3 -',code.encode());rest.setdefault(h,{})['return_marker_rc']=q.returncode
            time.sleep(6)
        (out/'restoration.json').write_text(json.dumps(rest,indent=2));connect_stable(c,OTHER)
if __name__=='__main__':main()
