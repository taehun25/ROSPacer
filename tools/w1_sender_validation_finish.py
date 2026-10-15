"""End owned guards, restore settings and preserve this validation campaign."""
import hashlib,json,shlex,signal,subprocess,tarfile,time
from pathlib import Path
from deploy import ROOT,REMOTE,ssh,KEY
from w1_b2 import Control,SR2,OTHER
from w1_ros45 import Campaign
from w1_closeout_audit import source
BASE=ROOT/'runs/w1_20261013_sender_validation'
class IPv6Control(Control):
    def extra(self,host,command,data=None):
        if host=='4':command=shlex.join(['ssh','-6','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.4','csilab@fe80::545b:21ad:4026:aa1b%wlp2s0',command])
        idx=subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-NetAdapter -Name 'Wi-Fi 2').ifIndex"],text=True).strip()
        return subprocess.run(['ssh','-6','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=5','-o','HostKeyAlias=192.168.0.5','csi@fe80::4f91:cec0:78f5:cc75%'+idx,command],input=data,capture_output=True,timeout=40)

def main(audit_only=False):
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11'
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'}
    record={'perf':{},'wire':{},'inhibitors':{},'checks':{},'hosts':{}}
    if audit_only:
        c=IPv6Control('192.168.0.4','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam.c=c
        record['recovery_transport']='existing Wi-Fi IPv6 link-local SSH; original IPv4 cleanup audit failed; no new root or authentication grants'
        for h in ['4','5']:
            record['perf'][h]=json.loads((BASE/('perf_'+h)/'restoration.json').read_text())
            record['wire'][h]=json.loads((BASE/('wire_'+h)/'restoration.json').read_text())
            record['inhibitors'][h]={'end_command_previously_succeeded':True}
    else:
        restore_owned(c,cam,record)
    time.sleep(3)
    for h in ['4','5']:record['hosts'][h]=c.python(h,source(h,'wlp2s0'))
    try:
        c.connect(SR2)
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            q=ssh(h,'python3 -',source(h,dev).encode());assert q.returncode==0,q.stderr;record['hosts'][h]=json.loads(q.stdout)
    finally:c.connect(OTHER)
    for h,r in record['hosts'].items():
        processes=r['processes']['stdout'];qdisc=json.loads(r['qdisc']['stdout'])
        checks={'noqueue':bool(qdisc) and all(x['kind']=='noqueue' for x in qdisc),'no_htb_classes':json.loads(r['classes']['stdout'].strip() or '[]')==[],
                'no_monitor':'type monitor' not in r['interfaces']['stdout'],
                'no_traffic':not any(x in processes for x in ['iperf3 -c','iperf3 -s','tools/traffic.py',' -m rospacer sender-observe','tools/w1_counter_worker.py']),
                'buffers_212992':all('net.core.'+k+' = 212992' in r['sysctl']['stdout'] for k in ['rmem_max','wmem_max'])}
        if h in ['4','5']:
            checks.update(power_restored='Power save: on' in r['power']['stdout'],cpu_restored=r['governors']==record['perf'][h]['governors_after'],
                          owned_ips_removed=not any(x.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(r['addresses']['stdout']) for x in d['addr_info']),
                          original_research_dds_unchanged=bool(r['research_libraries']) and all(x['unchanged'] for x in r['research_libraries'].values()),
                          owned_inhibitor_ended='FiniteSenderValidation' not in processes)
        record['checks'][h]=checks
    record['complete']=all(x for row in record['checks'].values() for x in row.values()) and all(x['restored'] for x in record['perf'].values()) and all(x['restored'] for x in record['wire'].values())
    (BASE/'final_restoration.json').write_text(json.dumps(record,indent=2))
    (BASE/'awake.end').write_text('end')
    print(json.dumps({'restoration_complete':record['complete'],'checks':record['checks']}),flush=True)
    if not record['complete']:raise RuntimeError('restoration check incomplete; see exact checks')
    preserve()

def restore_owned(c,cam,record):
    for h,home in cam.homes.items():
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/perf'
        q=c.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_session.py','end','--folder',folder,'--dev','wlp2s0']));assert q.returncode==0,q.stderr
        record['perf'][h]=json.loads(q.stdout);cam.archive(h,folder,BASE/('perf_'+h))
    # Confirm source is usable on Wi-Fi before removing the recovery route.
    q=c.extra('5','timeout -k 1 8 ssh -o BatchMode=yes -o ConnectTimeout=3 -o HostKeyAlias=192.168.0.4 csilab@192.168.0.4 hostname')
    record['wifi_before_wire_removal']={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
    if q.returncode:
        z=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert z.returncode==0,z.stderr
        q=c.extra('5','timeout -k 1 8 ssh -o BatchMode=yes -o ConnectTimeout=3 -o HostKeyAlias=192.168.0.4 csilab@192.168.0.4 hostname');assert q.returncode==0
        record['cleanup_reconnect_required']=True
    inhibitors=json.loads((BASE/'inhibitors.json').read_text())
    for h in ['4','5']:
        pid=inhibitors[h]['pid']
        code="import os,json,signal;from pathlib import Path;p="+str(pid)+"\nf=Path('/proc')/str(p)/'cmdline'\nif f.exists():\n s=f.read_bytes().replace(b'\\0',b' ').decode();assert 'FiniteSenderValidation' in s and os.getpgid(p)==p;os.killpg(p,signal.SIGTERM)\nprint(json.dumps({'ended_owned_group':p}))"
        q=c.extra(h,'sudo -n python3 -',code.encode());assert q.returncode==0,q.stderr;record['inhibitors'][h]=json.loads(q.stdout)
    c.ip4='192.168.0.4'
    for h,home in cam.homes.items():
        folder=home+'/'+REMOTE+'/runs/'+BASE.name+'/wire';address='192.168.50.2/24' if h=='4' else '192.168.50.1/24'
        q=c.extra(h,shlex.join(['sudo','-n','python3',home+'/'+REMOTE+'/tools/w1_management_guard.py','end','--folder',folder,'--address',address]));assert q.returncode==0,q.stderr
        record['wire'][h]=json.loads(q.stdout);cam.archive(h,folder,BASE/('wire_'+h))

def preserve():
    archive=BASE/'source_snapshot.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for folder in ['rospacer','tools','tests']:
            for p in sorted((ROOT/folder).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:tar.add(p,arcname=p.relative_to(ROOT))
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
        return h.hexdigest()
    files={}
    paths=list(BASE.rglob('*'))
    for rmw in ['fastdds','cyclonedds']:paths+=list((ROOT/'runs/w1_20261013_sender_only'/('dds_validation_'+rmw)).rglob('*'))
    for p in sorted(paths):
        if not p.is_file() or p.name in ['evidence_sha256.json','preservation.json']:continue
        files[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':digest(p)}
    (BASE/'evidence_sha256.json').write_text(json.dumps(files,indent=2))
    receipt={'files':len(files),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_source':True,'source_archive_sha256':digest(archive),'profile_sha256':digest(BASE/'frozen_profile.json'),'end_wall_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'note':'Campaign started2026-10-13; actual timestamps retained. Current dirty source is separate from historical per-run hashes.'}
    (BASE/'preservation.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'preserved_files':len(files)}),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--audit-only-ipv6',action='store_true');a=p.parse_args();main(a.audit_only_ipv6)
