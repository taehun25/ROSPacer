"""Verified W2 laboratory transports; no experiment starts on import."""
import json, subprocess, shlex, os
from pathlib import Path
from deploy import KEY, ROOT, REMOTE
from w1_b2 import Control, SR2, OTHER

HOSTS={'4':('csilab','fe80::545b:21ad:4026:aa1b','192.168.0.4','wlp2s0','3c:0a:f3:02:d9:3b'),
       '5':('csi','fe80::4f91:cec0:78f5:cc75','192.168.0.5','wlp2s0','3c:0a:f3:02:e4:c7'),
       '12':('csi2','fe80::5b13:c08f:4774:7b50','192.168.0.12','wlo1','50:e0:85:e9:54:ad'),
       '10':('csi','fe80::a055:52fc:be6c:3c16','192.168.0.10','wlp2s0','b8:1e:a4:a5:c8:c3')}

class Lab:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',self.folder)
        self.ap=None
        self.wired=False
        self.direct4=(self.folder/'direct4.json').exists()
        self.idx=subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-NetAdapter -Name 'Wi-Fi 2').ifIndex"],text=True).strip()
    def select(self,ap):
        if self.ap!=ap:self.c.connect(ap);self.ap=ap
    def ssh(self,h,cmd,data=None,root=False,timeout=45,via=None):
        # Hidden Windows OpenSSH must receive an explicit EOF. Inheriting the
        # invisible console stdin can leave a client alive after command exit.
        if data is None:data=b''
        if h=='4' and not via and (self.wired or not self.direct4):via='5'
        if h in ['5','12','10'] and self.ap==OTHER and not via:
            account,ll,alias,dev,mac=HOSTS[h]
            q=subprocess.run(['ssh','-4','-b',self.c.bind,'-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IPQoS=none','-o','ConnectTimeout=5','-o','HostKeyAlias='+alias,account+'@192.168.0.'+h,('sudo -n ' if root else '')+cmd],input=data,capture_output=True,timeout=timeout)
            if q.returncode:raise RuntimeError(f'host{h}: '+q.stderr.decode(errors='replace')[-1800:])
            return q.stdout
        account,ll,alias,dev,mac=HOSTS[h]
        if root:cmd='sudo -n '+cmd
        if via:
            ip='192.168.50.2' if self.wired and h=='4' and via=='5' else '192.168.50.1' if self.wired and h=='5' and via=='4' else '192.168.0.4' if h=='4' and via=='5' else ll+'%'+HOSTS[via][3]
            inner=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IPQoS=none','-o','ConnectTimeout=5','-o','HostKeyAlias='+alias,account+'@'+ip,cmd]
            return self.ssh(via,shlex.join(inner),data,timeout=timeout)
        q=subprocess.run(['ssh','-6','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IPQoS=none','-o','ConnectTimeout=5','-o','HostKeyAlias='+alias,account+'@'+ll+'%'+self.idx,cmd],input=data,capture_output=True,timeout=timeout)
        if q.returncode:raise RuntimeError(f'host{h}: '+q.stderr.decode(errors='replace')[-1800:])
        return q.stdout
    def py(self,h,source,root=False,timeout=45,via=None):
        return json.loads(self.ssh(h,'python3 -',source.encode(),root,timeout,via))
    def home(self,h):return '/home/'+HOSTS[h][0]+'/'+REMOTE
    def put(self,h,path,data,root=False,via=None):
        code='import sys;from pathlib import Path;p=Path('+repr(str(path))+');p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+".upload.pending");t.write_bytes(sys.stdin.buffer.read());t.replace(p)'
        self.ssh(h,'python3 -c '+shlex.quote(code),data,root=root,via=via)

def inventory(lab,h):
    dev=HOSTS[h][3];code='''import json,subprocess,hashlib\nfrom pathlib import Path\nr={}\n'''
    cmds={'hostname':['hostname'],'user':['id','-un'],'addresses':['ip','-j','addr'],'link':['iw','dev',dev,'link'],
          'qdisc':['tc','-j','qdisc','show','dev',dev],'clock':['chronyc','tracking'],'sources':['chronyc','-n','sources'],
          'sudo':['sudo','-n','id','-u'],'chrony_conf':['cat','/etc/chrony/chrony.conf'],'links':['ip','-j','link'],
          'runtime':['bash','-c','find ~/ros2_ws/src/large_data_1009/ROSPacer -maxdepth 2 -type d -name "runtime*"'],
          'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],
          'experiments':['pgrep','-af',r'[t]ools/traffic.py|[i]perf3 -[cs]|[r]ospacer sender-govern|[w]2_runner.py|[r]un_sweep'],
          'disk':['df','-h',str('/home/'+HOSTS[h][0])], 'time':['date','-Ins']}
    code+='for k,a in '+repr(cmds)+'.items():\n try:\n  p=subprocess.run(a,capture_output=True,text=True,timeout=3);r[k]={"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr}\n except subprocess.TimeoutExpired:r[k]={"rc":124,"stdout":"","stderr":"timeout"}\n'
    code+='r["mac"]=Path("/sys/class/net/'+dev+'/address").read_text().strip();print(json.dumps(r))'
    r=lab.py(h,code)
    if r['mac']!=HOSTS[h][4] or r['user']['stdout'].strip()!=HOSTS[h][0]:raise RuntimeError('identity mismatch '+h)
    if r['sudo']['stdout'].strip()!='0':raise RuntimeError('root unavailable '+h)
    return r

if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    folder=ROOT/'runs'/'w2_20261014_3rep';lab=Lab(folder);records={}
    try:
        for ap,hs in [(OTHER,['4','5']),(SR2,['12','10'])]:
            lab.select(ap)
            for h in hs:
                records[h]=inventory(lab,h);print(json.dumps({'host':h,'root':records[h]['sudo']['stdout'].strip(),'experiments':records[h]['experiments'],'runtime':records[h]['runtime'],'clock':records[h]['clock']},ensure_ascii=False),flush=True)
    finally:
        lab.select(OTHER);(folder/'preflight.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
