"""Restore only this campaign's settings and preserve its evidence."""
import hashlib,json,shlex,subprocess,tarfile,time
from pathlib import Path
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER
from w1_ros45 import Campaign
from w1_sender_validation_finish import IPv6Control
from w1_closeout_audit import source
from w1_ack_background import marker,sr2_peer,connect_stable
from w1_minphy_trial import HybridControl
BASE=ROOT/'runs/w1_20261014_ack_live'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def preserve():
    archive=BASE/'source_snapshot.tar.gz'
    with tarfile.open(archive,'w:gz') as tf:
        for folder in ['rospacer','tools','tests','docs']:
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:tf.add(p,arcname=p.relative_to(ROOT))
        for name in ['README.md','STATUS.md','pyproject.toml']:
            tf.add(ROOT/name,arcname=name)
    evidence={}
    for p in sorted(BASE.rglob('*')):
        if p.is_file() and p.name not in ['preservation.json','evidence_sha256.json']:
            evidence[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':digest(p)}
    (BASE/'evidence_sha256.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    r={'files':len(evidence),'source_archive_sha256':digest(archive),'index_sha256':digest(BASE/'evidence_sha256.json'),
       'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       'dirty_source':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
       'protocol_sha256':digest(BASE/'protocol.json'),'end_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
       'note':'Actual per-run source/profile hashes retained; current dirty source archive is separate; historical evidence unchanged.'}
    (BASE/'preservation.json').write_text(json.dumps(r,indent=2));print(json.dumps({'preserved_files':len(evidence)}),flush=True)

def main():
    c=HybridControl('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11'
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'}
    rec=json.loads((BASE/'cleanup_progress.json').read_text()) if (BASE/'cleanup_progress.json').exists() else {'peer':{},'perf':{},'wire':{},'hosts':{},'checks':{},'inhibitors':{}}
    def save(): (BASE/'cleanup_progress.json').write_text(json.dumps(rec,indent=2))
    try:
        connect_stable(c,SR2)
        for h in ['12','10']:
            if h not in rec['peer']:marker(h,'end')
        if len(rec['peer'])<2:time.sleep(8)
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            home='/home/'+('csi2' if h=='12' else 'csi');folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/background'+h
            q=sr2_peer(h,'python3 -',("import json,subprocess;from pathlib import Path;p=Path("+repr(folder)+");print(json.dumps({'restoration':json.loads((p/'restoration.json').read_text()),'profiles':subprocess.check_output(['nmcli','-g','NAME','connection','show'],text=True),'environment':None}))").encode())
            assert q.returncode==0,q.stderr;rec['peer'][h]=json.loads(q.stdout)
            assert rec['peer'][h]['restoration']['restored']
            assert ('ROSPacer-multiphy-peer12-AX' if h=='12' else 'ROSPacer-sender-validation-10-AX') not in rec['peer'][h]['profiles']
            q=sr2_peer(h,'python3 -',source(h,dev).encode());assert q.returncode==0,q.stderr;rec['hosts'][h]=json.loads(q.stdout);save()
    finally:connect_stable(c,OTHER)
    for h,home in cam.homes.items():
        if h in rec['perf']:
            assert rec['perf'][h]['restored'];continue
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/perf'
        q=c.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_session.py','end','--folder',folder,'--dev','wlp2s0']))
        assert q.returncode==0,q.stderr;rec['perf'][h]=json.loads(q.stdout);assert rec['perf'][h]['restored'];save()
        cam.archive(h,folder,BASE/('perf_'+h))
    # Preserve a working control path until all baseline settings are restored.
    ip6=IPv6Control('192.168.0.4','192.168.0.5','Wi-Fi 2',BASE);ip6.bind=c.bind
    probes={}
    for h in ['4','5']:
        q=ip6.extra(h,'hostname');probes[h]={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
        if h=='4' and q.returncode:
            z=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert z.returncode==0,z.stderr
            z=c.extra('4','sudo -n iw dev wlp2s0 set power_save on');assert z.returncode==0,z.stderr
            q=ip6.extra('4','hostname');rec['cleanup_source_reassociation_required']=True
        assert q.returncode==0,q.stderr
    rec['wifi_ipv6_before_wire_removal']=probes;save();cam.c=ip6
    for h,home in cam.homes.items():
        if h in rec['wire']:
            assert rec['wire'][h]['restored'];continue
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/wire';address='192.168.50.2/24' if h=='4' else '192.168.50.1/24'
        q=ip6.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_management_guard.py','end','--folder',folder,'--address',address]))
        assert q.returncode==0,q.stderr;rec['wire'][h]=json.loads(q.stdout);assert rec['wire'][h]['restored'];save()
        cam.archive(h,folder,BASE/('wire_'+h))
    session=json.loads((BASE/'session.json').read_text())
    for h in ['4','5']:
        if h in rec['inhibitors']:continue
        pid=session[h]['inhibitor']['pid']
        code="import os,signal,json;from pathlib import Path;p="+str(pid)+";f=Path('/proc')/str(p)/'cmdline'\nif f.exists():\n s=f.read_bytes().replace(b'\\0',b' ').decode();assert 'ACKLiveValidation' in s and os.getpgid(p)==p;os.killpg(p,signal.SIGTERM)\nprint(json.dumps({'ended_owned_group':p}))"
        q=ip6.extra(h,'sudo -n python3 -',code.encode());assert q.returncode==0,q.stderr;rec['inhibitors'][h]=json.loads(q.stdout);save()
    time.sleep(3)
    for h in ['4','5']:rec['hosts'][h]=ip6.python(h,source(h,'wlp2s0'));save()
    for h,r in rec['hosts'].items():
        ps=r['processes']['stdout'];qs=json.loads(r['qdisc']['stdout'])
        checks={'noqueue':bool(qs) and all(x['kind']=='noqueue' for x in qs),'no_htb':json.loads(r['classes']['stdout'].strip() or '[]')==[],
                'no_monitor':'type monitor' not in r['interfaces']['stdout'],
                'no_traffic':not any(x in ps for x in ['iperf3 -c','iperf3 -s','tools/traffic.py',' -m rospacer sender-observe','tools/w1_counter_worker.py',' -m rospacer.sender_ack_live --config',' -m rospacer.sender_ack_live --out',' -m rospacer.minphy_live',' -m tools.w1_minphy_worker']),
                'buffers_212992':all('net.core.'+k+' = 212992' in r['sysctl']['stdout'] for k in ['rmem_max','wmem_max'])}
        if h in ['4','5']:
            checks.update(power_restored='Power save: on' in r['power']['stdout'],cpu_restored=r['governors']==session[h]['perf']['baseline']['governors'],
                          no_owned_wire=not any(x.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(r['addresses']['stdout']) for x in d['addr_info']),
                          original_research_dds_unchanged=bool(r['research_libraries']) and all(x['unchanged'] for x in r['research_libraries'].values()),
                          no_owned_guards=not any(x in ps for x in ['ACKLiveValidation',BASE.name+'/perf',BASE.name+'/wire']),
                          modules_unchanged=r['kernel_modules']=={**session.get('module_placeholder',{}),**json.loads((BASE/'module_baseline.json').read_text())})
        else:checks['peer_AP_restored']='SSID: '+SR2+'\n' in r['link']['stdout'];checks['peer_guard_ended']='tools/w1_background_guard.py guard' not in ps and 'tools/w1_peer_ap_guard.py guard' not in ps
        rec['checks'][h]=checks
    (BASE/'awake.end').write_text('end');time.sleep(2)
    rec['complete']=all(v for row in rec['checks'].values() for v in row.values())
    (BASE/'final_restoration.json').write_text(json.dumps(rec,indent=2))
    print(json.dumps({'restoration_complete':rec['complete'],'checks':rec['checks']}),flush=True)
    preserve()
    if not rec['complete']:raise RuntimeError('Final restoration audit contains failed checks')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--preserve-only',action='store_true');a=p.parse_args()
    preserve() if a.preserve_only else main()
