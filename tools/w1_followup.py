"""Sequential correction/recovery/C2 stages, no competing measurements on host12."""
import json,subprocess,sys,time
from deploy import ROOT

RUN='w1_20261012_163000'
STEPS=[
 ['tools/w1_backpressure.py','--run',RUN,'--mode','smoke','--middleware','fastdds','--only-label','vendor','--suffix','_retry2'],
 ['tools/w1_backpressure.py','--run',RUN,'--middleware','cyclonedds','--suffix','_fragfix'],
 ['tools/w1_backpressure.py','--run',RUN,'--mode','smoke','--middleware','cyclonedds','--only-label','static','--suffix','_fragfix'],
 ['tools/w1_backpressure.py','--run',RUN,'--mode','smoke','--middleware','cyclonedds','--only-label','fixed','--suffix','_fragfix'],
 ['tools/w1_backpressure.py','--run',RUN,'--mode','smoke','--only-label','fixed','--suffix','_outage','--outage-seconds','5'],
 ['tools/w1_competition.py','--measure'],
]

def main():
    receipt=[];base=ROOT/'runs'/RUN
    for index,args in enumerate(STEPS):
        print('FOLLOWUP_STAGE '+str(index+1)+' '+str(args),flush=True)
        started=time.monotonic();q=subprocess.run([sys.executable,*args],cwd=ROOT)
        receipt.append({'args':args,'rc':q.returncode,'wall_seconds':time.monotonic()-started,'code_commit':'d7f6a81'})
        (base/'followup_receipt.json').write_text(json.dumps(receipt,indent=2))
        if q.returncode:raise RuntimeError('stage failed; preserve partial data and inspect')

if __name__=='__main__':main()
