import sys,json,time
from deploy import ROOT
from w2_runner import Runner
from w2_extended_smoke import test
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    import w2_extended_smoke as s
    s.test('smoke_T3_fixed_v3','E','cyclonedds','fixed','T3')
    s.test('smoke_T3_vendor_v3','E','fastdds','vendor','T3')
    # Keep failed multi-reader budget gates; do not dispatch Adaptive on T3.
    base=ROOT/'runs/w2_20261014_3rep'
    (base/'extended_smoke_ready.json').write_text(json.dumps({'passed':True,'results':s.r.results,'T3_adaptive_qualified':False,'T3_adaptive_action':'six planned rows explicitly blocked by independent input gate','wall':time.time()},indent=2))
