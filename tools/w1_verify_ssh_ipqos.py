"""A-B-A SSH IPQoS intervention and bounded two-way byte verification."""
import hashlib
import json
import shlex
import time
from deploy import ROOT
from w1_b2 import Control
from w1_ssh_repair import Relay

def main():
    base=ROOT/'runs/w1_20261013_ssh_repair'
    direct=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',base);direct.bind='192.168.0.11'
    relay=Relay('192.168.0.4','192.168.0.5','Wi-Fi 2',base);relay.bind='192.168.0.11'
    cfg='/etc/ssh/sshd_config.d/00-rospacer-wifi-ipqos.conf'
    backup='/home/csilab/ros2_ws/src/large_data_1009/ROSPacer/runs/'+base.name+'/ipqos_override.inactive'
    def root(source):
        q=relay.extra('4','sudo -n python3 -c '+shlex.quote(source))
        assert q.returncode==0,q.stderr
    moved=False
    try:
        root("from pathlib import Path;import subprocess;p=Path("+repr(cfg)+");b=Path("+repr(backup)+");assert p.read_text().endswith('IPQoS 0x00\\n') and not b.exists();p.rename(b);subprocess.run(['/usr/sbin/sshd','-t'],check=True);subprocess.run(['systemctl','reload','ssh'],check=True)")
        moved=True
        q=direct.extra('5',shlex.join(['timeout','-k','1','8','ssh','-o','HostKeyAlias=192.168.0.4','-o','BatchMode=yes','csilab@192.168.0.4','hostname']))
        old={'rc':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}
    finally:
        if moved:root("from pathlib import Path;import subprocess;p=Path("+repr(cfg)+");b=Path("+repr(backup)+");assert not p.exists();b.rename(p);subprocess.run(['/usr/sbin/sshd','-t'],check=True);subprocess.run(['systemctl','reload','ssh'],check=True)")
    repeats=[]
    for i in range(10):
        t=time.monotonic();r=direct.python('4',"import json,socket;print(json.dumps({'host':socket.gethostname()}))")
        assert r['host']=='csilab';repeats.append(time.monotonic()-t)
    payload=bytes(range(256))*4096
    digest=hashlib.sha256(payload).hexdigest()
    q=direct.extra('4',"python3 -c "+shlex.quote("import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"),payload)
    assert q.returncode==0 and q.stdout.decode().strip()==digest
    q=direct.extra('4',"python3 -c "+shlex.quote("import sys;sys.stdout.buffer.write(bytes(range(256))*4096)"))
    assert q.returncode==0 and hashlib.sha256(q.stdout).hexdigest()==digest
    audit={}
    for h in ['4','5']:
        audit[h]=direct.python(h,"import subprocess,json;r={}\nfor k,args in {'interfaces':['iw','dev'],'power':['iw','dev','wlp2s0','get','power_save'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],'addresses':['ip','-j','address']}.items():\n q=subprocess.run(args,capture_output=True,text=True,timeout=5);r[k]=q.stdout\nprint(json.dumps(r))")
    result={'old_qos_restored_test':old,'new_qos_repeated_successes':len(repeats),'ssh_seconds':repeats,'two_way_bytes_each':len(payload),'two_way_sha256':digest,'source_transport':'ordinary direct 5 Wi-Fi→AP→4 Wi-Fi SSH port22, no PC relay for validation','settings_audit':audit,'persistent_change':'4 SSH server IPQoS cs0/cs0; original configs retained; DDS and NIC settings unchanged'}
    (base/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ['old_qos_restored_test','new_qos_repeated_successes','two_way_bytes_each','source_transport']}))

if __name__=='__main__':main()
