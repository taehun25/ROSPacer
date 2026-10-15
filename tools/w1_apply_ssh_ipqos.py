"""Apply a validated SSH-only IPQoS workaround, preserving old configs."""
import json
import shlex
from deploy import ROOT,REMOTE
from w1_ssh_repair import Relay

def main():
    base=ROOT/'runs/w1_20261013_ssh_repair';c=Relay('192.168.0.4','192.168.0.5','Wi-Fi 2',base);c.bind='192.168.0.11'
    code="""import subprocess,json
from pathlib import Path
p=Path('/etc/ssh/sshd_config.d/00-rospacer-wifi-ipqos.conf')
body=CONTENT
before=subprocess.check_output(['/usr/sbin/sshd','-T'],text=True)
if p.exists():raise ValueError('preserve existing SSH override')
p.write_text(body);p.chmod(0o644)
try:
 subprocess.run(['/usr/sbin/sshd','-t'],check=True,capture_output=True)
 after=subprocess.check_output(['/usr/sbin/sshd','-T'],text=True)
 qos=[x for x in after.splitlines() if x.startswith('ipqos ')]
 if qos not in [['ipqos 0x00 0x00'],['ipqos cs0 cs0']]:raise ValueError('override did not become effective: '+str(qos))
 subprocess.run(['systemctl','reload','ssh'],check=True,capture_output=True)
except BaseException:
 p.unlink();subprocess.run(['systemctl','reload','ssh'],capture_output=True);raise
print(json.dumps({'created':str(p),'contents':body,'before_ipqos':[x for x in before.splitlines() if x.startswith('ipqos ')],'after_ipqos':qos,'sshd_config_valid':True,'reloaded':True}))
"""
    code='CONTENT='+repr('# ROSPacer SSH-only Wi-Fi workaround, verified 2026-10-13.\nIPQoS 0x00\n')+'\n'+code
    remote='/home/csilab/'+REMOTE+'/runs/'+base.name+'/apply_ipqos.py'
    q=c.extra('4','python3 -c '+shlex.quote('import sys;from pathlib import Path;Path('+repr(remote)+').write_bytes(sys.stdin.buffer.read())'),code.encode());assert q.returncode==0,q.stderr
    q=c.extra('4','sudo -n python3 '+shlex.quote(remote));assert q.returncode==0,q.stderr
    result=json.loads(q.stdout);(base/'applied_ipqos.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))

if __name__=='__main__':main()
