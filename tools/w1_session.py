"""Remote reversible W1 power/CPU settings, with an independent expiry guard."""
import argparse,json,os,subprocess,time
from pathlib import Path

def run(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=8)
    if p.returncode:raise RuntimeError(p.stderr or p.stdout)
    return p.stdout

def restore(folder):
    cfg=json.loads((folder/'baseline.json').read_text())
    result={'errors':[]}
    for name,val in cfg['sysctl'].items():
        try:run(['sysctl','-w',name+'='+str(val)])
        except Exception as e:result['errors'].append(str(e))
    try:run(['iw','dev',cfg['dev'],'set','power_save',cfg['power_save']])
    except Exception as e:result['errors'].append(str(e))
    for p,v in cfg['governors'].items():
        try:Path(p).write_text(v)
        except Exception as e:result['errors'].append(str(e))
    roots=json.loads(run(['tc','-j','qdisc','show','dev',cfg['dev']]))
    if any(q.get('root') and q.get('handle')=='7ac0:' for q in roots):
        try:run(['tc','qdisc','del','dev',cfg['dev'],'root','handle','7ac0:'])
        except Exception as e:result['errors'].append(str(e))
    result['qdisc_after']=json.loads(run(['tc','-j','qdisc','show','dev',cfg['dev']]))
    result['sysctl_after']={k:int(run(['sysctl','-n',k])) for k in cfg['sysctl']}
    result['power_save_after']=run(['iw','dev',cfg['dev'],'get','power_save'])
    result['governors_after']={p:Path(p).read_text().strip() for p in cfg['governors']}
    result['restored']=not result['errors'] and result['sysctl_after']==cfg['sysctl'] and result['governors_after']==cfg['governors'] and all(q['kind']=='noqueue' for q in result['qdisc_after']) and cfg['power_save'] in result['power_save_after']
    (folder/'restoration.json').write_text(json.dumps(result,indent=2))
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','end','guard']);p.add_argument('--folder',required=True);p.add_argument('--dev',required=True);p.add_argument('--expiry-seconds',type=int,default=3600);a=p.parse_args()
    if not 60<=a.expiry_seconds<=21600:p.error('expiry must be 60..21600 seconds')
    if os.geteuid()!=0:raise RuntimeError('root required')
    folder=Path(a.folder).resolve()
    if 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:raise ValueError('unexpected artifact path')
    if a.mode=='guard':
        deadline=time.monotonic()+a.expiry_seconds
        while time.monotonic()<deadline and not (folder/'end_session').exists():time.sleep(2)
        restore(folder)
        return
    if a.mode=='end':
        (folder/'end_session').write_text('end')
        print(json.dumps(restore(folder)));return
    roots=json.loads(run(['tc','-j','qdisc','show','dev',a.dev]))
    if any(q.get('root') and q['kind']!='noqueue' for q in roots):raise RuntimeError('preserve existing root')
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'baseline.json').exists():raise RuntimeError('session already exists')
    baseline={'dev':a.dev,'power_save':run(['iw','dev',a.dev,'get','power_save']).strip().split()[-1],
      'governors':{str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor')},
      'sysctl':{k:int(run(['sysctl','-n',k])) for k in ['net.core.rmem_max','net.core.wmem_max']},'qdisc':roots}
    (folder/'baseline.json').write_text(json.dumps(baseline,indent=2))
    guard=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder),'--dev',a.dev,'--expiry-seconds',str(a.expiry_seconds)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
    (folder/'guard_pid.json').write_text(json.dumps({'pid':guard.pid,'expiry_s':a.expiry_seconds}))
    try:
        run(['iw','dev',a.dev,'set','power_save','off'])
        for path in baseline['governors']:Path(path).write_text('performance')
        uid=int(os.environ.get('SUDO_UID',0));gid=int(os.environ.get('SUDO_GID',0))
        os.chown(folder,uid,gid)
        for file in folder.iterdir():os.chown(file,uid,gid)
    except Exception:
        restore(folder);raise
    print(json.dumps({'baseline':baseline,'guard_pid':guard.pid,'power_save':'off','cpu':'performance'}))

if __name__=='__main__':main()
