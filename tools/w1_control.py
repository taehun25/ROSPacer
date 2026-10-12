import argparse,json,shlex
from concurrent.futures import ThreadPoolExecutor
from deploy import ROOT,REMOTE,ssh

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','end']);p.add_argument('--run',required=True);a=p.parse_args()
    result={}
    def one(h):
        home={'12':'/home/csi2','10':'/home/csi'}[h];dev={'12':'wlo1','10':'wlp2s0'}[h]
        folder=home+'/'+REMOTE+'/runs/'+a.run
        args=['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_session.py',a.mode,'--folder',folder,'--dev',dev]
        q=ssh(h,shlex.join(args));report={'rc':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}
        return h,report
    with ThreadPoolExecutor(2) as pool:result=dict(pool.map(one,['12','10']))
    folder=ROOT/'runs'/a.run;folder.mkdir(parents=True,exist_ok=True)
    (folder/(a.mode+'_receipt.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if any(r['rc'] for r in result.values()):raise RuntimeError('session control failed; inspect both receipts')

if __name__=='__main__':main()
