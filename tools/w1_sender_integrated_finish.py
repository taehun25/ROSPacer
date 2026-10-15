"""Restore only this W1 campaign; keep sender installation and calibration key."""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
from deploy import ROOT, REMOTE
from w1_sender_integrated import BASE, control, collect
from w1_ack_background import connect_stable, sr2_peer
from w1_b2 import SR2, OTHER
from w1_closeout_audit import source


def finish():
    c=control();result={'hosts':{},'checks':{},'perf':{},'background':{}}
    # Both competitor hosts should already be on original SR2 after the batch.
    connect_stable(c,SR2)
    for h in ['12','10']:
        user='csi2' if h=='12' else 'csi';folder='/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
        code="import json,time;from pathlib import Path;p=Path("+repr(folder)+");f=p/'command.pending';f.write_text(json.dumps({'id':time.time_ns(),'action':'end'}));f.replace(p/'command.json')"
        q=sr2_peer(h,('sudo -n ' if h=='12' else '')+'python3 -',code.encode());assert q.returncode==0,q.stderr
    time.sleep(5)
    for h,dev in [('12','wlo1'),('10','wlp2s0')]:
        q=sr2_peer(h,'python3 -',source(h,dev).encode());assert q.returncode==0,q.stderr
        result['hosts'][h]=json.loads(q.stdout)
        user='csi2' if h=='12' else 'csi'
        q=sr2_peer(h,'cat '+shlex.quote('/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h+'/restoration.json'));assert q.returncode==0,q.stderr
        result['background'][h]=json.loads(q.stdout)
    connect_stable(c,OTHER)
    # Remove the temporary broad benchmark key, retaining only calibration access.
    pub=(BASE/'benchmark_public_key.txt').read_text().split()[1]
    c.python('5',"from pathlib import Path;f=Path.home()/'.ssh/authorized_keys';key="+repr(pub)+";f.write_text('\\n'.join(s for s in f.read_text().splitlines() if key not in s)+'\\n');print('{}')")
    c.python('4',"from pathlib import Path;\nfor name in ['id_ed25519_rospacer_w1bench','id_ed25519_rospacer_w1bench.pub']:\n p=Path.home()/'.ssh'/name\n if p.exists():p.unlink()\nprint('{}')")
    for h,user in [('5','csi'),('4','csilab')]:
        q=c.extra(h,shlex.join(['sudo','-n','python3','/home/'+user+'/'+REMOTE+'/tools/w1_session.py','end',
                              '--folder','/home/'+user+'/'+REMOTE+'/runs/'+BASE.name+'/perf','--dev','wlp2s0']))
        assert q.returncode==0,q.stderr;result['perf'][h]=json.loads(q.stdout)
    time.sleep(3)
    for h in ['4','5']:result['hosts'][h]=c.python(h,source(h,'wlp2s0'))
    for h,r in result['hosts'].items():
        proc=r['processes']['stdout'];roots=json.loads(r['qdisc']['stdout'])
        row={'noqueue':bool(roots) and all(q['kind']=='noqueue' for q in roots),
             'no_htb_classes':json.loads(r['classes']['stdout'].strip() or '[]')==[],
             'no_monitor':'type monitor' not in r['interfaces']['stdout'],
             'no_experiment_processes':not any(x in proc for x in ['iperf3 -c','iperf3 -s','tools/traffic.py','tools/w1_sender_local_smoke.py',' -m rospacer sender-govern']),
             'buffers_212992':all('net.core.'+k+' = 212992' in r['sysctl']['stdout'] for k in ['rmem_max','wmem_max'])}
        if h in ['4','5']:
            row.update(power_restored='Power save: on' in r['power']['stdout'],
                       cpu_restored=r['governors']==result['perf'][h]['governors_after'],
                       no_owned_wired_ips=not any(x.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(r['addresses']['stdout']) for x in d['addr_info']),
                       research_dds_unchanged=bool(r['research_libraries']) and all(v['unchanged'] for v in r['research_libraries'].values()))
        else:row.update(original_AP_restored='SSID: iptime5GAX1500SR2\n' in r['link']['stdout'],guard_restored=result['background'][h]['restored'])
        result['checks'][h]=row
    result['complete']=all(v for row in result['checks'].values() for v in row.values()) and all(r['restored'] for r in result['perf'].values())
    (BASE/'final_restoration.json').write_text(json.dumps(result,indent=2));print(json.dumps({'complete':result['complete'],'checks':result['checks']}),flush=True)
    if not result['complete']:raise RuntimeError('restoration incomplete')
    collect()


def preserve():
    archive=BASE/'source_snapshot.tar.gz'
    with tarfile.open(archive,'w:gz') as t:
        for name in ['rospacer','tools','tests','docs']:
            for p in (ROOT/name).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:t.add(p,arcname=p.relative_to(ROOT))
        for name in ['README.md','STATUS.md','EXECUTION_PLAN.md','pyproject.toml']:t.add(ROOT/name,arcname=name)
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    evidence={str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in BASE.rglob('*')
              if p.is_file() and p.name not in ['evidence_sha256.json','preservation.json']}
    (BASE/'evidence_sha256.json').write_text(json.dumps(evidence,indent=2))
    r={'files':len(evidence),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       'dirty_source':True,'source_sha256':sha(archive),'end_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (BASE/'preservation.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))


if __name__=='__main__':
    import sys
    preserve() if len(sys.argv)>1 and sys.argv[1]=='preserve' else finish()
