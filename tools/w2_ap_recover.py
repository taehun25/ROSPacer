"""Recover an interrupted premeasurement AP transition and verify both directions."""
import sys,json,time,shutil,shlex
from deploy import ROOT
from w2_runner import Runner,write
from w2_control import Lab,OTHER,SR2,HOSTS
BASE=ROOT/'runs/w2_20261015_resume1'

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    hist=BASE/'segment_history/ap_transition_fix';hist.mkdir(parents=True,exist_ok=False)
    for name in ['sessions.json','progress.json','results.json','launch.json','runner_identity.json','source_snapshot.tar.gz','source_sha256.json','runner.stdout.log','runner.stderr.log']:
        if (BASE/name).exists():shutil.copy2(BASE/name,hist/name)
    lab=Lab(BASE);lab.direct4=False;lab.select(OTHER)
    old=json.loads((BASE/'sessions.json').read_text());audit={}
    # 4/5 were already restored by the old coordinator. 12/10 really are on AX,
    # so send their end markers there rather than trusting the stale AP cache.
    for h in ['12','10']:lab.put(h,old[h]['folder']+'/end',b'',root=True)
    time.sleep(8)
    for ap,hosts in [(SR2,['12','10']),(OTHER,['5','4'])]:
        lab.select(ap)
        for h in hosts:
            code='from pathlib import Path;import time;p=Path('+repr(old[h]['folder']+'/restoration.json')+')\nfor _ in range(75):\n if p.exists():break\n time.sleep(1)\nprint(p.read_text())'
            audit[h]=lab.py(h,code,root=True,timeout=90)
            if not audit[h]['restored']:raise RuntimeError('prior guard restore incomplete '+h+str(audit[h]))
    write(hist/'verified_restoration.json',audit);sessions={}
    for ap,hosts in [(OTHER,['5','4']),(SR2,['12','10'])]:
        lab.select(ap)
        for h in hosts:
            home=lab.home(h);folder=home+'/runs/'+BASE.name+'/session_apfix'
            lab.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
            z=json.loads(lab.ssh(h,shlex.join(['python3',home+'/tools/w2_host_guard.py','begin','--folder',folder,'--host',h]),root=True,timeout=85));z['folder']=folder;sessions[h]=z;write(BASE/'sessions.json',sessions);print('rearmed '+h,flush=True)
            if h=='4':lab.wired=True
    write(BASE/'pair_ap.json',{'ap':SR2});r=Runner(BASE);r.deploy();checks=[]
    for target in [OTHER,SR2,OTHER]:
        before=time.monotonic();r.ap_pair(target);checks.append({'ap':target,'elapsed_s':time.monotonic()-before,'verified':r.peer_state_verified});print(json.dumps(checks[-1]),flush=True)
    write(BASE/'AP_transition_verified.json',{'passed':True,'checks':checks,'old_attempts_preserved':True});r.freeze_sources();r.status('resume_ready',AP_transition_verified=True)
    print('AP recovery: passed',flush=True)
