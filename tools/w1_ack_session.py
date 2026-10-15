"""Owned six-hour recovery, power and sleep guards for this campaign."""
import json,shlex,subprocess,sys
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_sender_validation_finish import IPv6Control
from w1_ros45 import Campaign
BASE=ROOT/'runs/w1_20261014_ack_live'

def main():
    c=IPv6Control('192.168.0.4','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};r={}
    for h,home in cam.homes.items():
        for name in ['tools/w1_management_guard.py','tools/w1_session.py']:
            cam.write(h,home+'/'+REMOTE+'/'+name,(ROOT/name).read_bytes())
        folder=home+'/'+REMOTE+'/runs/'+BASE.name
        q=c.extra(h,'python3 -c '+shlex.quote("from pathlib import Path;Path("+repr(folder)+").mkdir(parents=True,exist_ok=False)"));assert q.returncode==0,q.stderr
        r[h]={}
        for kind,args in [('wire',['tools/w1_management_guard.py','begin','--folder',folder+'/wire','--address','192.168.50.2/24' if h=='4' else '192.168.50.1/24','--expiry-seconds','21600']),('perf',['tools/w1_session.py','begin','--folder',folder+'/perf','--dev','wlp2s0','--expiry-seconds','21600'])]:
            q=c.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/'+args[0]]+args[1:]));assert q.returncode==0,q.stderr;r[h][kind]=json.loads(q.stdout)
        q=c.extra(h,'sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0
        r[h]['inhibitor']=c.python(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folder)+");q=subprocess.Popen(['sudo','-n','timeout','-k','2','21600','systemd-inhibit','--what=sleep:idle','--mode=block','--who=ROSPacer','--why=ACKLiveValidation','sleep','21590'],stdin=subprocess.DEVNULL,stdout=open(p/'inhibit.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    q=subprocess.Popen([sys.executable,str(ROOT/'tools/w1_local_awake.py'),'--folder',str(BASE)],stdin=subprocess.DEVNULL,stdout=open(BASE/'awake.log','w'),stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);r['PC']={'pid':q.pid}
    (BASE/'session.json').write_text(json.dumps(r,indent=2))
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11'
    proof=c.python('4',"import subprocess,json;print(json.dumps({'host':subprocess.check_output(['hostname'],text=True).strip(),'wire_ping':subprocess.run(['ping','-I','enp1s0','-c','1','-W','1','192.168.50.1'],stdout=subprocess.DEVNULL).returncode,'iwhelp':subprocess.check_output(['iw','help'],text=True),'capability':subprocess.check_output(['iw','phy','phy0','info'],text=True)}))")
    (BASE/'wired_proof.json').write_text(json.dumps(proof,indent=2));assert proof['wire_ping']==0
    print(json.dumps({'guarded_hosts':['4','5'],'six_hour_expiry':True,'wire_verified':True}),flush=True)
if __name__=='__main__':main()
