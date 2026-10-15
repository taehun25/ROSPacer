"""Finite W2 preparation/AP switch/restoration on a single verified laptop."""
import argparse,json,os,subprocess,time,signal
from pathlib import Path

def run(a,check=True):
    q=subprocess.run(a,capture_output=True,text=True,timeout=60 if a[:3]==['systemctl','restart','chrony'] else 15)
    if check and q.returncode:raise RuntimeError(str(a)+': '+q.stderr)
    return q.stdout.strip()

def restore(folder):
    cfg=json.loads((folder/'baseline.json').read_text()); errors=[]
    def attempt(a):
        try:run(a)
        except Exception as e:errors.append(str(e))
    attempt(['nmcli','radio','wifi','on'])
    attempt(['nmcli','connection','up','uuid',cfg['connection'],'ifname',cfg['dev']])
    if cfg.get('owned_uuid') and cfg['owned_uuid'] in run(['nmcli','-g','UUID','connection','show']).splitlines():attempt(['nmcli','connection','delete','uuid',cfg['owned_uuid']])
    attempt(['iw','dev',cfg['dev'],'set','power_save',cfg['power_save']])
    for k,v in cfg['sysctl'].items():attempt(['sysctl','-w',k+'='+str(v)])
    for k,v in cfg['governors'].items():
        try:Path(k).write_text(v)
        except Exception as e:errors.append(str(e))
    try:
        qs=json.loads(run(['tc','-j','qdisc','show','dev',cfg['dev']]))
        if any(q.get('handle')=='7ac0:' and q.get('root') for q in qs):attempt(['tc','qdisc','del','dev',cfg['dev'],'root','handle','7ac0:'])
    except Exception as e:errors.append(str(e))
    cp=Path('/etc/chrony/conf.d/rospacer-w2.conf')
    if cfg.get('owned_chrony'):
        if cp.exists():cp.unlink()
        attempt(['systemctl','restart','chrony'])
    for address in cfg.get('added_addresses',[]):
        current=json.loads(run(['ip','-j','address','show','dev','enp1s0']))
        if any(i['family']=='inet' and i['local']==address.split('/')[0] for d in current for i in d['addr_info']):attempt(['ip','address','del',address,'dev','enp1s0'])
    (folder/'restoration.json').write_text(json.dumps({'restored':not errors,'errors':errors,'qdisc':run(['tc','-j','qdisc','show','dev',cfg['dev']],False),'wall':time.time()},indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','guard','end']);p.add_argument('--folder',required=True);p.add_argument('--host',required=True,choices=['4','5','12','10']);a=p.parse_args()
    folder=Path(a.folder).resolve();dev='wlo1' if a.host=='12' else 'wlp2s0'
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts or not any(x.startswith('w2_') for x in folder.parts):raise ValueError('root and W2 folder required')
    if a.mode=='end':
        (folder/'end').touch()
        for _ in range(45):
            if (folder/'restoration.json').exists():print((folder/'restoration.json').read_text());return
            time.sleep(1)
        raise RuntimeError('guard restoration not acknowledged')
    if a.mode=='begin':
        folder.mkdir(parents=True,exist_ok=True)
        uid=int(os.environ.get('SUDO_UID',0));gid=int(os.environ.get('SUDO_GID',0))
        if uid:os.chown(folder.parent,uid,gid);os.chown(folder,uid,gid)
        if (folder/'baseline.json').exists():raise ValueError('session already exists')
        qs=json.loads(run(['tc','-j','qdisc','show','dev',dev]))
        if not all(q['kind']=='noqueue' for q in qs):raise ValueError('preserve existing shaper')
        cfg={'dev':dev,'host':a.host,'connection':run(['nmcli','-g','GENERAL.CON-UUID','device','show',dev]),
             'power_save':run(['iw','dev',dev,'get','power_save']).split()[-1],
             'sysctl':{k:int(run(['sysctl','-n',k])) for k in ['net.core.rmem_max','net.core.wmem_max','net.ipv4.ipfrag_time','net.ipv4.ipfrag_high_thresh']},
             'governors':{str(f):f.read_text().strip() for f in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor')},'added_addresses':[]}
        (folder/'baseline.json').write_text(json.dumps(cfg,indent=2))
        pid=subprocess.Popen(['systemd-inhibit','--what=sleep:idle','--mode=block','--who=ROSPacer-W2','--why=Finite W2 campaign','python3',str(Path(__file__).resolve()),'guard','--folder',str(folder),'--host',a.host],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True).pid
        try:
            run(['iw','dev',dev,'set','power_save','off'])
            for f in cfg['governors']:Path(f).write_text('performance')
            if a.host in ['4','5']:
                address='192.168.50.2/24' if a.host=='4' else '192.168.50.1/24'
                existing=json.loads(run(['ip','-j','address','show','dev','enp1s0']))
                if any(i['family']=='inet' for d in existing for i in d['addr_info']):raise ValueError('preserve existing Ethernet IPv4')
                run(['ip','link','set','dev','enp1s0','up']);run(['ip','address','add',address,'dev','enp1s0']);cfg['added_addresses']=[address]
                (folder/'baseline.json').write_text(json.dumps(cfg,indent=2))
                cp=Path('/etc/chrony/conf.d/rospacer-w2.conf')
                if cp.exists():raise ValueError('preserve existing W2 chrony config')
                cp.write_text('server 192.168.50.1 iburst minpoll 0 maxpoll 2 prefer\n' if a.host=='4' else 'local stratum 10\nallow 192.168.50.0/24\nallow 192.168.0.0/24\n')
                cfg['owned_chrony']=True;(folder/'baseline.json').write_text(json.dumps(cfg,indent=2));run(['systemctl','restart','chrony'])
            else:
                name='ROSPacer-W2-'+a.host+'-AX';run(['nmcli','connection','clone','iptime5GAX1500',name])
                uuid=run(['nmcli','-g','connection.uuid','connection','show',name]);cfg['owned_uuid']=uuid
                (folder/'baseline.json').write_text(json.dumps(cfg,indent=2))
                run(['nmcli','connection','modify','uuid',uuid,'connection.autoconnect','no','802-11-wireless.powersave','2','ipv4.method','manual','ipv4.addresses','192.168.0.'+a.host+'/24','ipv4.gateway','','ipv4.routes','','ipv4.never-default','yes','ipv6.method','ignore'])
        except BaseException:restore(folder);raise
        print(json.dumps({'ready':True,'pid':pid,'expiry_hours':26,'original_connection':cfg['connection']}),flush=True);return
    cfg=json.loads((folder/'baseline.json').read_text());deadline=time.monotonic()+26*3600;last=None
    try:
        while time.monotonic()<deadline and not (folder/'end').exists():
            f=folder/'command.json'
            if f.exists():
                try:m=json.loads(f.read_text())
                except ValueError:time.sleep(.5);continue
                if m.get('id')!=last and m.get('action') in ['ax','sr2']:
                    cfg=json.loads((folder/'baseline.json').read_text())
                    last=m['id'];uuid=cfg['owned_uuid'] if m['action']=='ax' else cfg['connection']
                    run(['nmcli','connection','up','uuid',uuid,'ifname',dev]);run(['iw','dev',dev,'set','power_save','off']);(folder/'state.json').write_text(json.dumps({'action':m['action'],'wall':time.time()}))
            time.sleep(1)
    finally:restore(folder)

if __name__=='__main__':main()
