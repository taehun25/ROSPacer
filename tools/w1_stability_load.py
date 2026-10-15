"""Finite loaded monitor-exit test, separate from idle lifecycle diagnostics."""
import json,shlex,time
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
BASE=ROOT/'runs/w1_20261014_sender_multiphy'
def main():
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};results=[]
    def probe():
        q=c.extra('5','timeout -k 1 7 ssh -o BatchMode=yes -o ConnectTimeout=3 -o HostKeyAlias=192.168.0.4 csilab@192.168.0.4 hostname');return {'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
    for mode in ['no_monitor_restore_on','monitor_keep_off','monitor_restore_on']:
        tag='loaded_'+mode;folders={h:home+'/'+REMOTE+'/runs/'+BASE.name+'/'+tag for h,home in cam.homes.items()}
        for h in cam.homes:c.python(h,"import json;from pathlib import Path;Path("+repr(folders[h])+").mkdir(parents=True,exist_ok=False);print('{}')")
        q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0
        q=c.extra('4','sudo -n iw dev wlp2s0 set power_save '+('on' if mode=='monitor_restore_on' else 'off'));assert q.returncode==0
        cam.launch('5',['timeout','-k','2','24','iperf3','-s','-1','-B','192.168.0.5','-p','55946','-J'],folders['5'],'server.json');time.sleep(.5)
        argv=['iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55946','-u','-b','100000000','-l','1400','-w','1048576','-t','10','-J']
        code="import sys,subprocess,json,time;sys.path.insert(0,"+repr(cam.homes['4']+'/'+REMOTE)+");from rospacer.sender_radio import SenderMonitor\nr={}\n"
        if mode.startswith('monitor'):
            code+="with SenderMonitor('wlp2s0') as m:\n m.configure_filter("+repr(json.loads((BASE/'frozen_profile.json').read_text()))+");q=subprocess.run("+repr(argv)+",capture_output=True,text=True,timeout=16);r.update(client_rc=q.returncode,stdout=q.stdout,stderr=q.stderr)\n"
        else:code+="q=subprocess.run("+repr(argv)+",capture_output=True,text=True,timeout=16);r.update(client_rc=q.returncode,stdout=q.stdout,stderr=q.stderr);subprocess.run(['iw','dev','wlp2s0','set','power_save','on'],check=True)\n"
        code+="r['power_after']=subprocess.check_output(['iw','dev','wlp2s0','get','power_save'],text=True);print(json.dumps(r))"
        q=c.extra('4','sudo -n python3 -',code.encode());r={'mode':mode,'command_rc':q.returncode,'client':json.loads(q.stdout) if q.returncode==0 else {'error':q.stderr.decode()}}
        time.sleep(2);r['ordinary_wifi_ssh_after']=probe()
        q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0;time.sleep(1);r['recovered_by_power_off']=probe()
        if r['recovered_by_power_off']['rc']:
            q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0;r['recovered_by_association']=probe();q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0
        for h in cam.homes:cam.archive(h,folders[h],BASE/tag/h)
        results.append(r);(BASE/'loaded_stability.json').write_text(json.dumps(results,indent=2));print(json.dumps({'mode':mode,'client_rc':r['client'].get('client_rc'),'exit_ssh':r['ordinary_wifi_ssh_after']['rc'],'off_recovery':r['recovered_by_power_off']['rc']}),flush=True)
if __name__=='__main__':main()
