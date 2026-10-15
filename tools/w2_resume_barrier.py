"""Freeze a consistent T3 barrier protocol; keep all pre-barrier observations."""
import json,sys,shutil,time
from pathlib import Path
from deploy import ROOT
from w2_runner import Runner,write
from w2_protocol import matrix
from w2_control import SR2

BASE=ROOT/'runs/w2_20261015_resume1'
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if not (BASE/'resume_ready.json').exists():raise RuntimeError('previous repaired-path tests must finish first')
    c=json.loads((BASE/'continuation.json').read_text(encoding='utf-8'))
    for row in matrix():
        if row['topology']!='T3' or row['mode']=='adaptive':continue
        p=BASE/'trials'/row['id'];s=p/'summary.json'
        if not s.exists():continue
        z=json.loads(s.read_text(encoding='utf-8'))
        if z.get('inherited_from')!=c['predecessor'] or z['status']!='measured':raise RuntimeError('preserve unexpected local T3 data '+str(p))
        dest=BASE/'predecessor_records_without_barrier'/row['id']
        if BASE.resolve() not in p.resolve().parents or BASE.resolve() not in dest.resolve().parents:raise RuntimeError('workspace boundary')
        dest.parent.mkdir(exist_ok=True);shutil.move(str(p),str(dest))
    c.update(retained_measured=33,rerun_all_T3=True,T3_barrier_protocol=True,pending_planned=168,T3_reason='warmup publish calls block beyond nominal start; independent publishers require a common post-warmup start marker; redo all 27 eligible T3 rows for a consistent protocol')
    write(BASE/'continuation.json',c)
    kept=[json.loads((BASE/'trials'/x['id']/'summary.json').read_text(encoding='utf-8')) for x in matrix() if (BASE/'trials'/x['id']/'summary.json').exists()]
    write(BASE/'results.json',kept)
    r=Runner(BASE);r.all_rows=matrix();r.results=kept;r.ap_pair(SR2);r.deploy()
    row={'id':'resume_smoke_T3_barrier','stage':'resume_smoke','topology':'T3','condition':'E','rho':1.5,'mode':'default','rmw':'fastdds','rep':0,'seconds':60,'warmup':10,'drain':30,'payload':1048576,'intent':'complete'}
    try:
        z=r.trial(row)
        if z['status']!='measured' or not z['received']:raise RuntimeError('shared T3 start gate failed')
        proof={k:z.get(k) for k in ['id','status','published','received','actual_start_offset_s','warmup_barrier']}
        write(BASE/'T3_barrier_verified.json',{'passed':True,'proof':proof});print(json.dumps(proof),flush=True)
    finally:r.cleanup_trial()
    r.ap_pair(SR2)
    ready=json.loads((BASE/'resume_ready.json').read_text(encoding='utf-8'));ready.update(T3_barrier_verified=True,T3_barrier_result=z,wall=time.time());write(BASE/'resume_ready.json',ready)
    r.status('resume_ready',T3_barrier_verified=True,pending_planned=168);print('barrier ready: passed',flush=True)
