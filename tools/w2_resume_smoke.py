"""Exercise the repaired paths, keeping smoke records outside formal repetitions."""
import sys,json,time
from deploy import ROOT
from w2_runner import Runner,write
from w2_protocol import matrix
from w2_control import SR2

BASE=ROOT/'runs/w2_20261015_resume1'

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');r=Runner(BASE);r.all_rows=matrix()
    r.results=json.loads((BASE/'results.json').read_text(encoding='utf-8'))
    r.ap_pair(SR2);r.deploy();checks=[]
    cases=[('resume_smoke_P0_low_0.6','T1','E','fastdds','default',.6,8,2,5),
           ('resume_smoke_F_fixed','T1','F','cyclonedds','fixed',.7,80,2,5),
           ('resume_smoke_T3_default','T3','E','fastdds','default',1.5,60,10,30),
           ('resume_smoke_B2_adaptive','T1','B2','fastdds','adaptive',.5,8,2,5)]
    for name,topology,condition,rmw,mode,rho,seconds,warmup,drain in cases:
        passed=False
        for attempt in range(1,3):
            row={'id':name+'_a'+str(attempt),'stage':'resume_smoke','topology':topology,'condition':condition,'rho':rho,'mode':mode,'rmw':rmw,'rep':0,'seconds':seconds,'warmup':warmup,'drain':drain,'payload':1048576,'intent':'complete'}
            try:
                z=r.trial(row);checks.append(z)
                passed=z['status']=='measured' and bool(z['received'])
                if topology=='T1':passed=passed and z['clock']['validated']
                print(json.dumps({k:z.get(k) for k in ['id','status','published','received','reason','actual_start_offset_s']}),flush=True)
                write(BASE/'resume_smoke_results.json',checks)
                r.status('resume_smoke',smoke_completed=len(checks),smoke_passed=passed)
            finally:r.cleanup_trial()
            if passed:break
        if not passed:raise RuntimeError('repaired-path smoke gate failed: '+name)
    r.ap_pair(SR2)
    write(BASE/'resume_ready.json',{'passed':True,'checks':checks,'wall':time.time(),'formal_repetitions_consumed':0})
    r.status('resume_ready',smoke_completed=len(checks));print('resume smoke: passed',flush=True)
