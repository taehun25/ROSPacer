"""Owned guard cleanup for sender RTPS observation campaign (no AP switching)."""
import hashlib,json,shlex,subprocess,tarfile,time
from pathlib import Path
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
from w1_sender_validation_finish import IPv6Control
from w1_closeout_audit import source
BASE=ROOT/'runs/w1_20261014_sender_bounded'
def preserve():
    def sha(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1048576),b''):h.update(b)
        return h.hexdigest()
    archive=BASE/'source_snapshot.tar.gz'
    with tarfile.open(archive,'w:gz') as tf:
        for folder in ['rospacer','tools','tests','docs']:
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:tf.add(p,arcname=p.relative_to(ROOT))
        tf.add(ROOT/'STATUS.md',arcname='STATUS.md')
    index={str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(BASE.rglob('*')) if p.is_file() and p.name not in ['preservation.json','evidence_sha256.json']}
    (BASE/'evidence_sha256.json').write_text(json.dumps(index,indent=2));(BASE/'preservation.json').write_text(json.dumps({'files':len(index),'source_sha256':sha(archive),'index_sha256':sha(BASE/'evidence_sha256.json'),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_source':True,'UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2));print(json.dumps({'preserved':len(index)}),flush=True)
def main():
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'}
    path=BASE/'cleanup_progress.json';r=json.loads(path.read_text()) if path.exists() else {'perf':{},'wire':{},'inhibitors':{},'checks':{},'hosts':{}}
    def save():path.write_text(json.dumps(r,indent=2))
    for h,home in cam.homes.items():
        if h in r['perf']:continue
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/perf';q=c.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_session.py','end','--folder',folder,'--dev','wlp2s0']));assert q.returncode==0,q.stderr;r['perf'][h]=json.loads(q.stdout);assert r['perf'][h]['restored'];save();cam.archive(h,folder,BASE/('perf_'+h))
    v=IPv6Control('192.168.0.4','192.168.0.5','Wi-Fi 2',BASE);v.bind=c.bind
    q=v.extra('4','hostname');r['source_wifi_before_wire_removal']={'rc':q.returncode,'err':q.stderr.decode()}
    if q.returncode:
        q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0,q.stderr;q=c.extra('4','sudo -n iw dev wlp2s0 set power_save on');assert q.returncode==0;r['cleanup_reassociation_required']=True
        q=v.extra('4','hostname');assert q.returncode==0,q.stderr
    save();cam.c=v
    for h,home in cam.homes.items():
        if h in r['wire']:continue
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/wire';q=v.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_management_guard.py','end','--folder',folder,'--address','192.168.50.2/24' if h=='4' else '192.168.50.1/24']));assert q.returncode==0,q.stderr;r['wire'][h]=json.loads(q.stdout);assert r['wire'][h]['restored'];save();cam.archive(h,folder,BASE/('wire_'+h))
    session=json.loads((BASE/'session.json').read_text())
    for h in ['4','5']:
        if h in r['inhibitors']:continue
        pid=session[h]['inhibitor']['pid'];code="import os,signal,json;from pathlib import Path;p="+str(pid)+";f=Path('/proc')/str(p)/'cmdline'\nif f.exists():\n s=f.read_bytes().replace(b'\\0',b' ').decode();assert 'SenderProtocolValidation' in s and os.getpgid(p)==p;os.killpg(p,signal.SIGTERM)\nprint(json.dumps({'ended_owned_group':p}))"
        q=v.extra(h,'sudo -n python3 -',code.encode());assert q.returncode==0,q.stderr;r['inhibitors'][h]=json.loads(q.stdout);save()
    time.sleep(3)
    for h in ['4','5']:
        data=v.python(h,source(h,'wlp2s0'));r['hosts'][h]=data;ps=data['processes']['stdout'];qs=json.loads(data['qdisc']['stdout'])
        r['checks'][h]={'noqueue':bool(qs) and all(x['kind']=='noqueue' for x in qs),'no_htb':json.loads(data['classes']['stdout'].strip() or '[]')==[],
            'no_monitor':'type monitor' not in data['interfaces']['stdout'],'power_restored':'Power save: on' in data['power']['stdout'],'cpu_restored':data['governors']==session[h]['perf']['baseline']['governors'],
            'buffers_restored':all('net.core.'+k+' = 212992' in data['sysctl']['stdout'] for k in ['rmem_max','wmem_max']),
            'no_owned_wire':not any(x.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(data['addresses']['stdout']) for x in d['addr_info']),
            'no_experiment_processes':not any(x in ps for x in ['tools/traffic.py','iperf3 -c','iperf3 -s',' -m rospacer.sender_protocol','SenderProtocolValidation',BASE.name+'/wire',BASE.name+'/perf']),
            'research_dds_unchanged':bool(data['research_libraries']) and all(x['unchanged'] for x in data['research_libraries'].values()),
            'modules_unchanged':data['kernel_modules']==json.loads((ROOT/'runs/w1_20261014_sender_multiphy/frozen_profile.json').read_text())['module_srcversions']};save()
    (BASE/'awake.end').write_text('end');r['complete']=all(x for row in r['checks'].values() for x in row.values());(BASE/'final_restoration.json').write_text(json.dumps(r,indent=2));print(json.dumps({'restored':r['complete'],'checks':r['checks']}),flush=True);preserve()
    assert r['complete'],'restoration audit incomplete'
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--preserve-only',action='store_true');a=p.parse_args();preserve() if a.preserve_only else main()
