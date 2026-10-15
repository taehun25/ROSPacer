"""Read-only verification of the user-installed laptop10 sudo rule."""
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from deploy import ROOT, KEY
from w1_b2 import Control, SR2, OTHER


def main():
    stamp = datetime.now(timezone.utc).strftime('w2_sudo_check_%Y%m%d_%H%M%S')
    folder = ROOT/'runs'/stamp
    folder.mkdir()
    c = Control('192.168.0.4','192.168.0.5','Wi-Fi 2',folder)
    record = {'changed_laptop_configuration': False, 'started_experiment': False}
    code = r'''
import json, pathlib, subprocess
def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=8)
    return {'rc':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}
r={'hostname':run(['hostname']), 'account':run(['id','-un']),
   'mac':pathlib.Path('/sys/class/net/wlp2s0/address').read_text().strip(),
   'link':run(['iw','dev','wlp2s0','link'])}
if r['mac']!='b8:1e:a4:a5:c8:c3' or r['account']['stdout']!='csi' or 'SSID: iptime5GAX1500SR2' not in r['link']['stdout']:
    raise RuntimeError('laptop10 identity or original AP mismatch')
r['root_id']=run(['sudo','-n','/usr/bin/id','-u'])
r['root_python']=run(['sudo','-n','/usr/bin/python3','-c','import os;print(os.geteuid())'])
r['sudo_rule']=run(['sudo','-n','cat','/etc/sudoers.d/rospacer-w2'])
r['syntax']=run(['sudo','-n','visudo','-c'])
r['verified']=all(r[k]['rc']==0 for k in ['root_id','root_python','sudo_rule','syntax']) and r['root_id']['stdout']=='0' and r['root_python']['stdout']=='0' and 'csi ALL=(root) NOPASSWD: ALL' in r['sudo_rule']['stdout']
print(json.dumps(r))
'''
    try:
        c.connect(SR2)
        idx = subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-NetAdapter -Name 'Wi-Fi 2').ifIndex"],text=True).strip()
        q=subprocess.run(['ssh','-6','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.10','csi@fe80::a055:52fc:be6c:3c16%'+idx,'python3 -'],input=code.encode(),capture_output=True,timeout=45)
        record['ssh_rc']=q.returncode
        if q.returncode:
            record['error']=q.stderr.decode(errors='replace')
        else:
            record['laptop10']=json.loads(q.stdout)
    finally:
        c.connect(OTHER)
        record['pc_restored_ssid']=OTHER
        (folder/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    result=record.get('laptop10',{})
    print(json.dumps({'report':str(folder/'result.json'),'verified':result.get('verified',False),'root_id':result.get('root_id'),'root_python':result.get('root_python'),'syntax':result.get('syntax'),'error':record.get('error'),'pc_restored':record.get('pc_restored_ssid')}),flush=True)
    if not result.get('verified'):raise SystemExit(1)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
