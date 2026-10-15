"""Bounded direct-Wi-Fi TCP diagnosis using the already established PC relay."""
import json
from pathlib import Path
import shlex
import time
from deploy import ROOT,REMOTE
from w1_b2 import Control

class Relay(Control):
    def extra(self,host,command,data=None):
        if host=='4':
            command=shlex.join(['timeout','-k','2','24','ssh','-p','55936','-o','HostKeyAlias=192.168.0.4','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','csilab@127.0.0.1',command])
        return super().extra('5',command,data)

def main():
    base=ROOT/'runs/w1_20261013_ssh_repair';base.mkdir(exist_ok=True)
    c=Relay('192.168.0.4','192.168.0.5','Wi-Fi 2',base);c.bind='192.168.0.11'
    homes={'4':'/home/csilab','5':'/home/csi'};folders={h:home+'/'+REMOTE+'/runs/'+base.name for h,home in homes.items()}
    inv={}
    for h in homes:
        inv[h]=c.python(h,"import subprocess,json;from pathlib import Path;Path("+repr(folders[h])+").mkdir(exist_ok=True);r={}\nfor k,args in {'host':['hostname'],'link':['iw','dev','wlp2s0','link'],'iface':['iw','dev'],'routes':['ip','-j','route'],'neighbors':['ip','neigh','show'],'offload':['sudo','-n','ethtool','-k','wlp2s0'],'firewall':['sudo','-n','iptables-save'],'rp_filter':['sysctl','net.ipv4.conf.all.rp_filter','net.ipv4.conf.wlp2s0.rp_filter'],'ss':['ss','-tin']}.items():\n q=subprocess.run(args,capture_output=True,text=True,timeout=6);r[k]={'rc':q.returncode,'out':q.stdout,'err':q.stderr}\nprint(json.dumps(r))")
    (base/'inventory.json').write_text(json.dumps(inv,indent=2),encoding='utf8')
    for h in homes:
        code="import subprocess,json;from pathlib import Path;p=Path("+repr(folders[h])+");q=subprocess.Popen(['sudo','-n','timeout','-s','INT','-k','2','13','tcpdump','-i','wlp2s0','-s','128','-w',str(p/'tcp.pcap'),'host 192.168.0.4 and host 192.168.0.5 and tcp port 22'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=open(p/'capture.log','w'),start_new_session=True);print(json.dumps({'pid':q.pid}))"
        c.python(h,code)
    time.sleep(1)
    q=c.extra('5',shlex.join(['timeout','-k','1','9','ssh','-o','BatchMode=yes','-o','HostKeyAlias=192.168.0.4','csilab@192.168.0.4','hostname']))
    (base/'failed_direct.json').write_text(json.dumps({'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}))
    time.sleep(5)
    for h in homes:
        dest=base/h;dest.mkdir(exist_ok=True)
        for name in ['tcp.pcap','capture.log']:
            q=c.extra(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0,q.stderr;(dest/name).write_bytes(q.stdout)
        q=c.extra(h,'tcpdump -tt -nn -r '+shlex.quote(folders[h]+'/tcp.pcap'));assert q.returncode==0,q.stderr;(dest/'tcp.txt').write_bytes(q.stdout)
    print(json.dumps({'captured':True,'failed_direct_rc':json.loads((base/'failed_direct.json').read_text())['rc']}))

if __name__=='__main__':main()
