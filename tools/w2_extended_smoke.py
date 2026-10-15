"""Preflight the actual competing/outage/two-reader paths before unattended use."""
import json,sys,time
from deploy import ROOT
from w2_runner import Runner
BASE=ROOT/'runs/w2_20261014_3rep'
r=Runner(BASE)
def test(name,condition,rmw,mode,topology='T1',seconds=8):
    row={'id':name,'stage':'smoke','topology':topology,'condition':condition,'rho':.2,'mode':mode,'rmw':rmw,'rep':0,'seconds':seconds,'warmup':2,'drain':5,'payload':1048576,'intent':'complete'}
    try:
        z=r.trial(row);r.results.append(z);r.status('extended_smoke');print(json.dumps({k:z.get(k) for k in ['id','status','published','received','p99_ms','reason']}),flush=True)
        if z['status']!='measured' or not z['received']:raise RuntimeError('smoke validity failed')
    finally:r.cleanup_trial()
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    test('smoke_C2_fixed_v2','C2','cyclonedds','fixed')
    test('smoke_D3_fixed_v2','D3','fastdds','fixed',seconds=28)
    r.prepare_t3()
    test('smoke_T3_fixed_v1','E','cyclonedds','fixed','T3')
    test('smoke_T3_adaptive_v1','E','fastdds','adaptive','T3')
    (BASE/'extended_smoke_ready.json').write_text(json.dumps({'passed':True,'results':r.results,'wall':time.time()},indent=2))
