"""Check co-channel dispatch and the last vendor/outage helpers before launch."""
import json,time,sys
from deploy import ROOT
from w2_control import SR2
from w2_runner import write
import w2_extended_smoke as s

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    s.r.ap_pair(SR2)
    s.r.deploy()
    s.test('smoke_B2_adaptive_v1','B2','fastdds','adaptive',seconds=8)
    s.test('smoke_Clean_cyclone_vendor_v1','Clean','cyclonedds','vendor')
    s.test('smoke_D3_fixed_v3','D3','fastdds','fixed',seconds=28)
    write(ROOT/'runs/w2_20261014_3rep/final_paths_ready.json',{'passed':True,'results':s.r.results,'wall':time.time()})
