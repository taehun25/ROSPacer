"""End original power session, wait its guard, then begin a fresh bounded phase."""
import json
import shlex
from deploy import ROOT,REMOTE
from w1_b2 import Control,OTHER,SR2


def main():
    out=ROOT/'runs/w1_20261012_radio45';c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',out)
    receipts={}
    try:
        c.connect(OTHER)
        for h,home in [('4','/home/csilab'),('5','/home/csi')]:
            folder=home+'/'+REMOTE+'/runs/w1_20261012_radio45'
            q=c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_session.py end --folder '+folder+' --dev wlp2s0');assert q.returncode==0,q.stderr
            receipts[h]={'old_end':json.loads(q.stdout)}
        for h,home in [('4','/home/csilab'),('5','/home/csi')]:
            folder=home+'/'+REMOTE+'/runs/w1_20261012_radio45'
            code="import time,json;from pathlib import Path;p=Path("+repr(folder+'/guard_pid.json')+");pid=json.loads(p.read_text())['pid'];end=time.monotonic()+10\nwhile Path('/proc',str(pid),'cmdline').exists() and Path('/proc',str(pid),'cmdline').read_bytes() and time.monotonic()<end:time.sleep(.2)\nassert not Path('/proc',str(pid),'cmdline').exists() or not Path('/proc',str(pid),'cmdline').read_bytes(),'old guard still alive';print('{}')"
            q=c.extra(h,'sudo -n python3 -',code.encode());assert q.returncode==0,q.stderr
            q=c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_session.py begin --folder '+folder+'/session_phase2 --dev wlp2s0');assert q.returncode==0,q.stderr
            receipts[h]['new_begin']=json.loads(q.stdout)
            q=c.extra(h,'sudo -n sysctl -w net.core.rmem_max=1048576 net.core.wmem_max=1048576');assert q.returncode==0,q.stderr
    finally:
        (out/'renewal_receipt.json').write_text(json.dumps(receipts,indent=2));c.connect(SR2)
    print(json.dumps({'old_restored':{h:r['old_end']['restored'] for h,r in receipts.items()},'phase2_guard_s':3600}))


if __name__=='__main__':main()
