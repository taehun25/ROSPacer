"""Read-only final lab audit and content-addressed W1 evidence preservation."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from deploy import ROOT,ssh
from w1_b2 import Control,SR2,OTHER

BASE=ROOT/'runs/w1_20261013_w1_closeout'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def baselines(h):
    values={}
    base=ROOT/'runs/w1_20261012_radio45/ros45'
    for p in base.rglob('*.metadata.json'):
        if p.parent.name!=h:continue
        for path,digest in json.loads(p.read_text()).get('libraries',{}).items():
            values.setdefault(path,{'sha256':digest,'baseline_metadata':str(p.relative_to(ROOT))})
    return values

def source(h,dev):
    return 'BASELINES='+repr(baselines(h))+'\nDEV='+repr(dev)+'\n'+"""
import subprocess,json,hashlib
from pathlib import Path
r={}
for k,args in {'host':['hostname'],'kernel':['uname','-r'],'link':['iw','dev',DEV,'link'],'interfaces':['iw','dev'],'qdisc':['tc','-j','qdisc','show','dev',DEV],'classes':['tc','-j','class','show','dev',DEV],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],'addresses':['ip','-j','address'],'processes':['ps','-eo','pid,args'],'power':['iw','dev',DEV,'get','power_save']}.items():
 q=subprocess.run(args,capture_output=True,text=True,timeout=6);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
r['research_libraries']={}
for name,old in BASELINES.items():
 p=Path(name)
 try:digest=hashlib.sha256(p.read_bytes()).hexdigest()
 except OSError:digest=None
 r['research_libraries'][name]={**old,'current_sha256':digest,'unchanged':digest==old['sha256']}
r['kernel_modules']={p.parent.name:p.read_text().strip() for p in Path('/sys/module').glob('*/srcversion') if p.parent.name in ['mt76','mt7921e','mt792x_lib','iwlwifi','rtw89_8852be']}
r['governors']={str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_governor')}
headers=list(Path('/usr/src').glob('linux-headers-'+r['kernel']['stdout'].strip().replace('-generic','')+'*/include/net/ieee80211_radiotap.h'))
header=headers[0] if headers else Path('/absent-radiotap-header')
r['radiotap_definitions']=[x for x in header.read_text().splitlines() if any(v in x for v in ['LTF','DOPPLER','PRE_FEC','PAD','PE_DISAMBIG','KNOWN']) and ('HE_DATA' in x or 'HE_MU' in x)] if header.exists() else []
print(json.dumps(r))
"""

def main():
    BASE.mkdir(exist_ok=True);c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11'
    results={}
    for h in ['4','5']:results[h]=c.python(h,source(h,'wlp2s0'))
    try:
        c.connect(SR2)
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            q=ssh(h,'python3 -',source(h,dev).encode());assert q.returncode==0,q.stderr;results[h]=json.loads(q.stdout)
    finally:c.connect(OTHER)
    (BASE/'raw_environment_audit.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    checks={}
    for h,r in results.items():
        processes=r['processes']['stdout']
        qdisc=json.loads(r['qdisc']['stdout'])
        checks[h]={'noqueue':all(q['kind']=='noqueue' for q in qdisc) and bool(qdisc),
                   'no_htb_classes':r['classes']['rc']==0 and json.loads(r['classes']['stdout'].strip() or '[]')==[],
                   'no_monitor':'type monitor' not in r['interfaces']['stdout'],
                   'no_experiment_processes':not any(x in processes for x in ['tools/traffic.py',' -m rospacer govern',' -m rospacer sender-observe','iperf3 -c','iperf3 -s','tools/w1_monitor_guard.py','tools/w1_counter_worker.py']),
                   'buffers_212992':all('net.core.'+k+' = 212992' in r['sysctl']['stdout'] for k in ['rmem_max','wmem_max'])}
        if h in ['4','5']:
            checks[h]['no_owned_wired_ips']=not any(a.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(r['addresses']['stdout']) for a in d['addr_info'])
            checks[h]['research_dds_unchanged']=bool(r['research_libraries']) and all(v['unchanged'] for v in r['research_libraries'].values())
    record={'hosts':results,'checks':checks,'all_checks_passed':all(v for row in checks.values() for v in row.values()),'scope':'read-only current check; research-library equality limited to recorded pre-fixed-runtime mappings'}
    (BASE/'current_restoration_audit.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps({'checks':checks,'all_checks_passed':record['all_checks_passed']}),flush=True)
    preserve()

def preserve():
    # Source snapshots are separate from historical per-run source hashes.
    archive=BASE/'current_source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name in ['rospacer','tools','tests','docs']:
            for p in sorted((ROOT/name).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:tar.add(p,arcname=p.relative_to(ROOT))
        for name in ['README.md','STATUS.md','EXECUTION_PLAN.md','pyproject.toml']:
            tar.add(ROOT/name,arcname=name)
    artifacts={};counts={}
    for folder in sorted((ROOT/'runs').iterdir()):
        if not folder.is_dir() or not folder.name.startswith('w1_2026101'):continue
        total=0
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts:continue
            if p in [BASE/'evidence_sha256.json',BASE/'preservation.json']:continue
            artifacts[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':sha(p)};total+=1
        counts[folder.name]=total
    (BASE/'evidence_sha256.json').write_text(json.dumps(artifacts,indent=2),encoding='utf8')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    state={'file_count':len(artifacts),'by_folder':counts,'git_commit':commit,'dirty_source':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),'source_snapshot_sha256':sha(archive),'index_sha256':sha(BASE/'evidence_sha256.json'),'environment_audit_sha256':sha(BASE/'current_restoration_audit.json'),'note':'content hashes preserve current evidence; historical runs retain their original source hashes, not replaced by current archive'}
    (BASE/'preservation.json').write_text(json.dumps(state,indent=2),encoding='utf8')
    print(json.dumps({'hashed_artifacts':len(artifacts),'source_snapshot_sha256':state['source_snapshot_sha256']}),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--preserve-only',action='store_true');a=p.parse_args()
    preserve() if a.preserve_only else main()
