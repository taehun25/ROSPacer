"""Reproduce hidden-console SSH EOF handling without touching lab configuration."""
import sys,time,json,subprocess
from deploy import ROOT,KEY
sys.stdout.reconfigure(encoding='utf-8')
base=ROOT/'runs/w2_20261014_3rep'
argv=['ssh','-4','-b','192.168.0.11','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IPQoS=none','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.5','csi@192.168.0.5','tc -j qdisc show dev wlp2s0']
result=[]
for mode,payload in [('inherited_console',None),('explicit_EOF',b'')]:
    begin=time.monotonic()
    try:
        p=subprocess.run(argv,input=payload,capture_output=True,timeout=8)
        result.append({'mode':mode,'rc':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace'),'seconds':time.monotonic()-begin})
    except subprocess.TimeoutExpired:result.append({'mode':mode,'timeout':True,'seconds':time.monotonic()-begin})
(base/'hidden_ssh_probe.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
