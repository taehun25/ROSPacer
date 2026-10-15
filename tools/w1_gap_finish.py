"""Verify restoration over Ethernet, return final receipt over bounded UDP.

This preserves the original power settings even if Wi-Fi SSH stalls. No
experimental input or controller feedback is added; traffic has already ended.
"""
import hashlib
import json
import secrets
import shlex
import time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER

CHECK="""import json,subprocess
from pathlib import Path
r={}
for k,args in {'interfaces':['iw','dev'],'link':['iw','dev',DEV,'link'],'qdisc':['tc','-j','qdisc','show','dev',DEV],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],'power':['iw','dev',DEV,'get','power_save'],'addresses':['ip','-j','address'],'processes':['ps','-eo','pid,args']}.items():
 q=subprocess.run(args,capture_output=True,text=True,timeout=6);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
r['governors']={str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_governor')}
print(json.dumps(r))
"""

def main():
    base=ROOT/'runs/w1_20261013_sender_gap';c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',base);c.bind='192.168.0.11'
    reports={h:c.python(h,"DEV='wlp2s0'\n"+CHECK) for h in ['4','5']}
    for h in ['4','5']:
        r=reports[h]
        assert not any(s in r['interfaces']['stdout'] for s in ['rpmon','w1mon'])
        assert all(q['kind']=='noqueue' for q in json.loads(r['qdisc']['stdout']))
        assert all('net.core.'+k+' = 212992' in r['sysctl']['stdout'] for k in ['rmem_max','wmem_max'])
        assert 'Power save: on' in r['power']['stdout']
        assert not any(s in r['processes']['stdout'] for s in ['tools/traffic.py',' -m rospacer sender-observe','iperf3 -c','iperf3 -s','tools/w1_monitor_guard.py','tools/w1_counter_worker.py'])
    assert all(v=='powersave' for v in reports['4']['governors'].values())
    (base/'pre_wire_removal_audit.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
    token=secrets.token_hex(32)
    folder5='/home/csi/'+REMOTE+'/runs/'+base.name
    listener="""import hashlib,hmac,json,socket,time
from pathlib import Path
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('192.168.0.5',55935));s.settimeout(1);deadline=time.monotonic()+45
while time.monotonic()<deadline:
 try:data,peer=s.recvfrom(4096)
 except socket.timeout:continue
 if peer[0]!='192.168.0.4':continue
 try:
  msg=json.loads(data);body=msg['body'].encode();mac=hmac.new(bytes.fromhex(TOKEN),body,hashlib.sha256).hexdigest()
  if not hmac.compare_digest(mac,msg['mac']):continue
  Path(OUT).write_bytes(body);break
 except (ValueError,KeyError):continue
else:raise RuntimeError('final source receipt timeout')
s.close()
"""
    code='TOKEN='+repr(token)+'\nOUT='+repr(folder5+'/source_final_receipt.json')+'\n'+listener
    launch="import json,subprocess;from pathlib import Path;p=Path("+repr(folder5)+");q=subprocess.Popen(['timeout','-k','2','48','python3','-c',"+repr(code)+"],stdin=subprocess.DEVNULL,stdout=open(p/'receipt_listener.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))"
    c.python('5',launch);time.sleep(.5)
    folder4='/home/csilab/'+REMOTE+'/runs/'+base.name
    source="""import sys,json,hashlib,hmac,socket,time,subprocess
from pathlib import Path
sys.path.insert(0,TOOLS)
from w1_management_guard import restore
folder=Path(FOLDER)/'wire';(folder/'end').write_text('end');receipt=restore(folder)
receipt['interfaces']=subprocess.check_output(['iw','dev'],text=True)
receipt['wifi_power']=subprocess.check_output(['iw','dev','wlp2s0','get','power_save'],text=True)
receipt['qdisc']=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))
body=json.dumps(receipt).encode();data=json.dumps({'body':body.decode(),'mac':hmac.new(bytes.fromhex(TOKEN),body,hashlib.sha256).hexdigest()}).encode()
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('192.168.0.4',0))
for _ in range(8):s.sendto(data,('192.168.0.5',55935));time.sleep(.25)
s.close();Path(FOLDER+'/source_final_receipt.json').write_bytes(body)
"""
    code='TOKEN='+repr(token)+'\nTOOLS='+repr('/home/csilab/'+REMOTE+'/tools')+'\nFOLDER='+repr(folder4)+'\n'+source
    # Detach before deleting this SSH connection's local address.
    launcher="import json,subprocess;from pathlib import Path;p=Path("+repr(folder4)+");q=subprocess.Popen(['sudo','-n','timeout','-k','2','12','python3','-c',"+repr('import time;time.sleep(1)\n'+code)+"],stdin=subprocess.DEVNULL,stdout=open(p/'final_receipt.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))"
    c.python('4',launcher);time.sleep(5)
    q=c.extra('5','cat '+shlex.quote(folder5+'/source_final_receipt.json'));assert q.returncode==0,q.stderr
    reports['source_final_receipt']=json.loads(q.stdout);assert reports['source_final_receipt']['restored']
    assert 'Power save: on' in reports['source_final_receipt']['wifi_power']
    q=c.extra('5','sudo -n python3 /home/csi/'+REMOTE+'/tools/w1_management_guard.py end --folder '+folder5+'/wire --address 192.168.50.1/24');assert q.returncode==0,q.stderr
    reports['wire5_restoration']=json.loads(q.stdout);assert reports['wire5_restoration']['restored']
    reports['5']=c.python('5',"DEV='wlp2s0'\n"+CHECK)
    try:
        c.connect(SR2)
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            q=ssh(h,'python3 -',("DEV="+repr(dev)+'\n'+CHECK).encode());assert q.returncode==0,q.stderr
            reports[h]=json.loads(q.stdout)
            assert not any(s in reports[h]['processes']['stdout'] for s in ['iperf3 -c','iperf3 -s','tools/traffic.py'])
    finally:c.connect(OTHER)
    reports['restored']=True;reports['source_wifi_ssh_qualified']=False
    reports['notes']='settings/processes/owned Ethernet addresses restored; source original Wi-Fi SSH remains unreliable despite working ping, accepted SSH auth and TCP retransmission; final owned-address receipt authenticated from source Wi-Fi UDP after removal'
    (base/'final_restoration.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
    print(json.dumps({'restored':True,'hosts':['4','5','12','10'],'owned_addresses_removed':True,'source_wifi_ssh_qualified':False}))

if __name__=='__main__':main()
