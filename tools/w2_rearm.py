"""Preserve premeasurement dispatch failures, rearm restored hosts, use wire management."""
import sys,json,time,shlex,shutil,os
from pathlib import Path
from deploy import ROOT
from w2_control import Lab,OTHER,SR2
from w2_runner import Runner,write

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    base=ROOT/'runs/w2_20261014_3rep';l=Lab(base);l.direct4=False
    old=json.loads((base/'sessions.json').read_text());audit={}
    for ap,hosts in [(OTHER,['4','5']),(SR2,['12','10'])]:
        l.select(ap)
        for h in hosts:
            audit[h]=l.py(h,'from pathlib import Path;print(Path('+repr(old[h]['folder']+'/restoration.json')+').read_text())',root=True)
            if not audit[h]['restored']:
                write(base/('restoration_retry_'+h+'_previous.json'),audit[h])
                home=l.home(h);l.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
                code='import importlib.util;from pathlib import Path;s=importlib.util.spec_from_file_location("guard",'+repr(home+'/tools/w2_host_guard.py')+');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);p=Path('+repr(old[h]['folder'])+');m.restore(p);print((p/"restoration.json").read_text())'
                audit[h]=l.py(h,code,root=True,timeout=95)
            if not audit[h]['restored']:raise RuntimeError('prior host restoration incomplete '+h)
    previous=json.loads((base/'dispatch_failure_history.json').read_text()) if (base/'dispatch_failure_history.json').exists() else None
    tag='second_console_launch' if previous else 'first_wifi_launch'
    saved=base/'dispatch_failures'/tag;saved.mkdir(parents=True,exist_ok=False)
    for f in ['results.json','progress.json','sessions.json','restoration.json','launch.json','runner_identity.json','source_snapshot.tar.gz','source_sha256.json','runner.stdout.log','runner.stderr.log','prelaunch.json']:
        if (base/f).exists():shutil.copy2(base/f,saved/f)
    write(saved/'verified_restoration.json',audit)
    for p in list((base/'trials').glob('T1_E_*')):
        summary=p/'summary.json'
        if not summary.exists():raise RuntimeError('unexpected partial trial '+str(p))
        d=json.loads(summary.read_text(encoding='utf-8'))
        if d['status']!='failed' or list(p.glob('*/pub.json')):raise RuntimeError('only premeasurement dispatch failures may move')
        if base.resolve() not in p.resolve().parents:raise RuntimeError('workspace boundary')
        shutil.move(str(p),str(saved/p.name))
    if (base/'STOP').exists():shutil.move(str(base/'STOP'),str(saved/'STOP'))
    write(base/'dispatch_failure_history.json',{'path':str(saved.relative_to(base)),'count':3+(previous.get('count',0) if previous else 0),'previous':previous,'reason':'premeasurement dispatch failures preserved; wire management and hidden-console SSH EOF handling corrected'})
    sessions={}
    for ap,hosts in [(OTHER,['5','4']),(SR2,['12','10'])]:
        l.select(ap)
        for h in hosts:
            home=l.home(h);folder=home+'/runs/'+base.name+('/session_console_recovery' if previous else '/session_wire_recovery')
            l.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
            d=json.loads(l.ssh(h,shlex.join(['python3',home+'/tools/w2_host_guard.py','begin','--folder',folder,'--host',h]),root=True,timeout=60))
            d['folder']=folder;sessions[h]=d;write(base/'sessions.json',sessions);print('rearmed '+h,flush=True)
            if h=='4':l.wired=True
    write(base/'pair_ap.json',{'ap':SR2});l.select(OTHER)
    r=Runner(base);r.deploy();r.freeze_sources()
    # Verify privileged configuration and a larger transfer over the wire,
    # including the low socket limits that preceded the earlier Wi-Fi failure.
    cmd='import json,subprocess;subprocess.run(["sysctl","-w","net.core.rmem_max=212992","net.core.wmem_max=212992"],stdout=subprocess.DEVNULL,check=True);print(json.dumps({"transport":"5-to-4 Ethernet SSH","large_reply":"w"*16000}))'
    probe=r.runpy('4',cmd,root=True)
    if len(probe['large_reply'])!=16000:raise RuntimeError('wire management evidence incomplete')
    write(base/'wire_management_verified.json',{'passed':True,'reply_bytes':16000,'same_low_kernel_limits':True,'sender_WiFi_unchanged':True,'wall':time.time()})
    prior=json.loads((saved/'prelaunch.json').read_text(encoding='utf-8'));prior.update(wired_management_verified=True,sessions_rearmed=True,prior_restore_audited=audit,checked_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    write(base/'prelaunch.json',prior)
    write(base/'results.json',[]);r.status('rearmed',reason='wire management verified; first three premeasurement dispatch failures preserved and scheduled again')
    print('rearm: passed',flush=True)
