"""Unattended finite B2 input qualification; APs and original buffers restored."""
import argparse,json,shlex,subprocess,sys,time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER

def remote(h,source):
    q=ssh(h,'python3 -',source.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return json.loads(q.stdout)

def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);a=p.parse_args()
    if not a.tag.replace('_','').isalnum():p.error('single tag')
    base=ROOT/'runs/w1_20261013_sender_validation';out=base/(a.tag+'_background');out.mkdir(exist_ok=False)
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',out);homes={'12':'/home/csi2','10':'/home/csi'}
    folders={h:home+'/'+REMOTE+'/runs/'+base.name+'/'+out.name for h,home in homes.items()};old={};launched=None;guard_start=None
    def start(h,args,name):
        return remote(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folders[h])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(name)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    try:
        c.connect(SR2);inventory={}
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            inventory[h]=remote(h,"import subprocess,json;print(json.dumps({'link':subprocess.check_output(['iw','dev',"+repr(dev)+",'link'],text=True),'info':subprocess.check_output(['iw','dev',"+repr(dev)+",'info'],text=True),'processes':subprocess.check_output(['ps','-eo','args'],text=True)}))")
            assert 'SSID: '+SR2+'\n' in inventory[h]['link'] and 'channel 149 ' in inventory[h]['info'] and 'width: 80 MHz' in inventory[h]['info']
            assert not any(x in inventory[h]['processes'] for x in ['iperf3 -c','iperf3 -s','tools/traffic.py'])
            old[h]=remote(h,"import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k])) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
            q=ssh(h,'sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0
        (out/'inventory.json').write_text(json.dumps(inventory,indent=2));(out/'baseline.json').write_text(json.dumps(old,indent=2))
        # Background sysctls get an independent finite restoration even if this PC disconnects.
        for h in homes:
            code="import subprocess,time;time.sleep(100);subprocess.run("+repr(['sudo','-n','sysctl','-w']+[k+'='+str(v) for k,v in old[h].items()])+")"
            start(h,['timeout','-k','2','108','python3','-c',code],'buffer_guard.log')
        guard_start=time.monotonic()
        start('10',['timeout','-k','2','85','iperf3','-s','-1','-B','192.168.0.4','-p','55942','-J','-i','.2'],'server.json');time.sleep(.5)
        code="import subprocess,json,time;start=time.time();q=subprocess.run(['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55942','-u','-b','300000000','-l','1400','-w','1048576','-t','75','-i','.2','-J'],capture_output=True,text=True,timeout=80);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_wall':start,'end_wall':time.time()}))"
        start('12',['timeout','-k','2','83','python3','-u','-c',code],'client.json');launched=time.monotonic()
        c.connect(OTHER)
        subprocess.run([sys.executable,str(ROOT/'tools/w1_sender_validate_run.py'),'--tag',a.tag,'--rate-mbps','0','--seconds','24'],cwd=ROOT,check=True)
        time.sleep(max(0,launched+87-time.monotonic()))
        c.connect(SR2)
        for h,name in [('12','client.json'),('10','server.json')]:
            q=ssh(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0;(out/(h+'_'+name)).write_bytes(q.stdout)
        # Inspect optional C2 helper only; absence does not authorize privileged AP switching.
        q=ssh('10','test -f /home/csi/'+REMOTE+'/runs/'+base.name+'/background10/baseline.json')
        (base/'c2_readiness.json').write_text(json.dumps({'root_helper_prepared':q.returncode==0,'scope':'C2 requires previously requested bounded AP-switch helper; skip if absent.'},indent=2))
        data=json.loads((out/'12_client.json').read_text());result={'client_rc':data['rc'],'scope':'continuous requested300Mb/s 12→SR2→10, main saturated4→AX→5; both149/80; frozen input validation, not proposal2s ON/OFF performance trial','source_data':data}
        (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({'B2':a.tag,'background_rc':data['rc']}),flush=True)
    finally:
        try:
            if guard_start:time.sleep(max(0,min(55,guard_start+110-time.monotonic())))
            c.connect(SR2);rest={}
            for h,v in old.items():
                q=ssh(h,'sudo -n sysctl -w '+shlex.join([k+'='+str(x) for k,x in v.items()]));rest[h]={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
            (out/'restoration.json').write_text(json.dumps(rest,indent=2))
        finally:c.connect(OTHER)
if __name__=='__main__':main()
