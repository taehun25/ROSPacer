"""Real qdisc lifecycle checks on sender; no receiver access."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);a=p.parse_args();base=Path(a.base);folder=base/'lifecycle_checks';folder.mkdir(exist_ok=False)
    results={};console='/home/csilab/.local/bin/rospacer';bundle=base/'calibration_controlled'
    validations=[base/n/'validation.json' for n in ['validation_clean_controlled','validation_B2_controlled','validation_C2_controlled_r1']]
    def qdisc():return json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))
    def args(out,seconds):
        cmd=[console,'sender-govern','--bundle',str(bundle),'--out',str(out),'--mode','fixed','--seconds',str(seconds)]
        for v in validations:cmd+=['--validation',str(v)]
        return cmd
    if not all(q['kind']=='noqueue' for q in qdisc()):raise RuntimeError('preserve active experiment')
    for name,signum,seconds in [('sigterm',signal.SIGTERM,30),('sigkill_expiry',signal.SIGKILL,5)]:
        before=qdisc();child=subprocess.Popen(args(folder/name,seconds),stdout=open(folder/(name+'.log'),'w'),stderr=subprocess.STDOUT,start_new_session=True)
        installed=False
        for _ in range(30):
            if any(q['kind']=='htb' for q in qdisc()):installed=True;break
            if child.poll() is not None:break
            time.sleep(.1)
        if not installed:raise RuntimeError('controller failed to install; inspect logs')
        time.sleep(.8);os.kill(child.pid,signum);child.wait(timeout=5)
        for _ in range(32):
            if all(q['kind']=='noqueue' for q in qdisc()):break
            time.sleep(.5)
        after=qdisc();results[name]={'installed_htb':installed,'returncode':child.returncode,'qdisc_before':before,'qdisc_after':after,
                                   'restored':all(q['kind']=='noqueue' for q in after),'signal':int(signum)}
        if not results[name]['restored']:raise RuntimeError('expiry rollback failed')
    cmd=[console,'sender-govern','--bundle',str(base/'calibration'),'--out',str(folder/'should_not_exist'),
         '--validation',str(base/'validation_clean/validation.json'),'--validation',str(base/'validation_B2/validation.json'),'--seconds','5']
    q=subprocess.run(cmd,capture_output=True,text=True);results['failed_validation_rejected']={'returncode':q.returncode,'stderr':q.stderr,
         'rejected':q.returncode!=0 and not (folder/'should_not_exist').exists(),'qdisc_unchanged':all(r['kind']=='noqueue' for r in qdisc())}
    (folder/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results),flush=True)


if __name__=='__main__':main()
