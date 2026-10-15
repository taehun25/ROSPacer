"""Separate power-only and monitor/power lifecycle; QoS and PS recovery probes."""
import argparse,json,shlex,time
from deploy import ROOT,REMOTE
from w1_b2 import Control
from w1_ros45 import Campaign
BASE=ROOT/'runs/w1_20261014_sender_multiphy'

def main():
    p=argparse.ArgumentParser();p.add_argument('--fresh-association',action='store_true');p.add_argument('--prefix',default='stability');a=p.parse_args()
    if not a.prefix.replace('_','').isalnum():p.error('single prefix')
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11';cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'};results=[]
    def ssh_probe(qos=None):
        args=['timeout','-k','1','7','ssh','-o','BatchMode=yes','-o','ConnectTimeout=3','-o','HostKeyAlias=192.168.0.4']
        if qos:args+=['-o','IPQoS='+qos]
        args+=['csilab@192.168.0.4','hostname'];a=time.monotonic();q=c.extra('5',shlex.join(args));return {'rc':q.returncode,'seconds':time.monotonic()-a,'out':q.stdout.decode(),'err':q.stderr.decode()}
    for mode in ['power_only','monitor_off','monitor_restore_on']:
        for rep in range(2):
            tag=a.prefix+'_'+mode+'_'+str(rep+1);folder=cam.homes['4']+'/'+REMOTE+'/runs/'+BASE.name+'/'+tag
            c.python('4',"import json;from pathlib import Path;Path("+repr(folder)+").mkdir(parents=True,exist_ok=False);print('{}')")
            if a.fresh_association:
                q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0,q.stderr
            q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0
            before=ssh_probe();r={'tag':tag,'mode':mode,'rep':rep+1,'before':before,'fresh_association_before_case':a.fresh_association}
            cam.launch('4',['sudo','-n','timeout','-s','INT','-k','2','24','tcpdump','-i','wlp2s0','-s','96','-w',folder+'/wifi.pcap','arp','or','tcp','port','22'],folder,'capture.log')
            if mode=='power_only':
                q=c.extra('4','sudo -n iw dev wlp2s0 set power_save on');assert q.returncode==0;time.sleep(3)
            else:
                power='on' if mode=='monitor_restore_on' else 'off'
                q=c.extra('4','sudo -n iw dev wlp2s0 set power_save '+power);assert q.returncode==0
                code="import sys,json,time;sys.path.insert(0,"+repr(cam.homes['4']+'/'+REMOTE)+");from rospacer.sender_radio import SenderMonitor\nwith SenderMonitor('wlp2s0'):time.sleep(3)\nprint(json.dumps({'monitor_context_closed':True}))"
                q=c.extra('4','sudo -n python3 -',code.encode());r['context']={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()};time.sleep(1)
            r['after_default']=ssh_probe();r['after_qos_none']=ssh_probe('none')
            q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0;time.sleep(1)
            r['after_power_off_no_reassociate']=ssh_probe()
            if r['after_power_off_no_reassociate']['rc']:
                q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');r['reassociate']={'rc':q.returncode,'out':q.stdout.decode(),'err':q.stderr.decode()}
                r['after_reassociate']=ssh_probe()
            r['final']=c.python('4',"import subprocess,json;print(json.dumps({'interfaces':subprocess.check_output(['iw','dev'],text=True),'power':subprocess.check_output(['iw','dev','wlp2s0','get','power_save'],text=True),'link':subprocess.check_output(['iw','dev','wlp2s0','link'],text=True)}))")
            (BASE/(tag+'.json')).write_text(json.dumps(r,indent=2));results.append(r);(BASE/(a.prefix+'_summary.json')).write_text(json.dumps(results,indent=2))
            print(json.dumps({'mode':mode,'rep':rep+1,'default':r['after_default']['rc'],'qos_none':r['after_qos_none']['rc'],'power_off_without_reassociate':r['after_power_off_no_reassociate']['rc']}),flush=True)
    # Only archive completed finite capture processes.
    time.sleep(26)
    for r in results:
        tag=r['tag'];folder=cam.homes['4']+'/'+REMOTE+'/runs/'+BASE.name+'/'+tag;cam.archive('4',folder,BASE/tag/'4')
if __name__=='__main__':main()
