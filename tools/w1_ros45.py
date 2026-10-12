"""Wired-clock qualified W1 ROS comparator smoke on laptops4/5.

All processes are bounded. Wired DDS is rejected by a finite guard while
NTP and SSH remain available. Raw logs and actual library hashes retained.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import xml.etree.ElementTree as E
import sys

from deploy import ROOT,REMOTE
from w1_b2 import Control,OTHER,SR2
from w1_backpressure import analyze_telemetry
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize
from rospacer import profiles
from rospacer.clock import qualify_pair
from rospacer.metrics import analyze_pair


class Campaign:
    def __init__(self,a):
        self.a=a;self.out=ROOT/'runs'/a.run/(('ros45_stock' if a.pinned else 'ros45')+('_bp' if a.backpressure else ''));self.out.mkdir(parents=True,exist_ok=True)
        self.c=Control(a.ip4,a.ip5,'Wi-Fi 2',self.out)
        self.homes={'4':'/home/csilab','5':'/home/csi'};self.ips={'4':a.ip4,'5':a.ip5}
        cal=ROOT/'runs'/a.run/'calibration'
        self.C0=json.loads((cal/'summary.json').read_text())['C0_receiver_median_bps']/8
        import re
        self.rtt=float(re.search(r'= [0-9.]+/([0-9.]+)/',json.loads((cal/'ping.json').read_text())['stdout'])[1])/1000
        self.commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        self.hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['rospacer','tools'] for p in (ROOT/folder).glob('*.py')}

    def write(self,h,path,data):
        script='import sys;from pathlib import Path;p=Path('+repr(path)+');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sys.stdin.buffer.read())'
        q=self.c.extra(h,'python3 -c '+shlex.quote(script),data)
        if q.returncode:raise RuntimeError(q.stderr.decode())

    def deploy(self):
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as tf:
            for folder in ['rospacer','tools']:
                for f in (ROOT/folder).glob('*.py'):tf.add(f,arcname=folder+'/'+f.name)
        for h,home in self.homes.items():
            code='import sys,tarfile;from pathlib import Path\np=Path('+repr(home+'/'+REMOTE)+')\nwith tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as tf:\n for m in tf:\n  parts=Path(m.name).parts\n  if len(parts)!=2 or parts[0] not in ["rospacer","tools"] or not m.isfile():raise RuntimeError("invalid source member")\n  q=p.joinpath(*parts);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(tf.extractfile(m).read())'
            q=self.c.extra(h,'python3 -c '+shlex.quote(code),buf.getvalue())
            if q.returncode:raise RuntimeError(q.stderr.decode())

    def launch(self,h,argv,folder,log):
        return self.c.python(h,'import subprocess,json;from pathlib import Path;p=Path('+repr(folder)+');p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen('+repr(argv)+',cwd='+repr(self.homes[h]+'/'+REMOTE)+',stdin=subprocess.DEVNULL,stdout=open(p/'+repr(log)+',"w"),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({"pid":q.pid}))')

    def archive(self,h,folder,dest):
        script='import sys,tarfile;from pathlib import Path\np=Path('+repr(folder)+')\nwith tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz") as tf:\n for f in p.iterdir():\n  if f.is_file():tf.add(f,arcname=f.name)'
        q=self.c.extra(h,'python3 -',script.encode())
        if q.returncode:raise RuntimeError(q.stderr.decode())
        dest.mkdir(parents=True,exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(q.stdout),mode='r:gz') as tf:
            for m in tf:
                if '/' in m.name or not m.isfile():raise RuntimeError('invalid artifact member')
                (dest/m.name).write_bytes(tf.extractfile(m).read())

    def profile(self,rmw,label,h,cfg,path):
        if rmw=='cyclonedds' and label=='default':
            root=E.Element('CycloneDDS',xmlns='https://cdds.io/config');d=E.SubElement(root,'Domain',Id='any');g=E.SubElement(d,'General');interfaces=E.SubElement(g,'Interfaces');E.SubElement(interfaces,'NetworkInterface',name='wlp2s0');profiles.write_xml(root,path)
            profiles.validate(path,ROOT/'reference/cyclonedds-0.10.5.xsd');return
        if rmw=='fastdds':profiles.fastdds(cfg,path,self.ips[h])
        else:profiles.cyclone(cfg,path,'wlp2s0',self.ips['5' if h=='4' else '4'])
        if label=='vendor':
            tree=E.parse(path);root=tree.getroot()
            if rmw=='fastdds':
                ns={'d':'http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles'};col=root.find('d:profiles',ns)
                for endpoint in list(col):
                    if endpoint.tag.split('}')[-1] in ['publisher','subscriber']:col.remove(endpoint)
                col.remove(col.find('d:transport_descriptors',ns));rtps=col.find('d:participant/d:rtps',ns)
                for field in list(rtps):rtps.remove(field)
                for tag,value in [('useBuiltinTransports','true'),('sendSocketBufferSize','1048576'),('listenSocketBufferSize','4194304')]:E.SubElement(rtps,'{'+ns['d']+'}'+tag).text=value
            else:
                ns={'d':'https://cdds.io/config'};d=root.find('d:Domain',ns);g=d.find('d:General',ns);inn=d.find('d:Internal',ns)
                for field in list(g):
                    if field.tag.split('}')[-1] in ['MaxMessageSize','FragmentSize']:g.remove(field)
                for field in list(inn):
                    if field.tag.split('}')[-1] not in ['SocketSendBufferSize','SocketReceiveBufferSize']:inn.remove(field)
            E.register_namespace('',ns['d']);tree.write(path,encoding='utf-8',xml_declaration=True)
        profiles.validate(path,ROOT/'reference'/('fastdds-2.6.10-local-validation.xsd' if rmw=='fastdds' else 'cyclonedds-0.10.5.xsd'))

    def trial(self,rmw,label):
        name=rmw+'_'+label;local=self.out/name
        if (local/'summary.json').exists():return
        local.mkdir(parents=True,exist_ok=True)
        duration=self.a.seconds;hz=(.8 if self.a.backpressure else .2)*self.C0/1048576;count=math.ceil(hz*duration)
        cfg=synthesize(1048576,hz,1,self.C0,self.rtt,1)
        cfg.update(dev='wlp2s0',peers=[self.ips['5']],middleware=rmw,relay_in_survey=None,airtime_overhead_s=None,survey_semantics_validated=False)
        cfg['cap_packet_Bps']=(.5 if self.a.backpressure else .9)*self.C0
        cfg['cap_application_Bps']=cfg['cap_packet_Bps']/cfg['packet_factor']
        cfg['experiment_cap_definition']='HTB packet bytes/sec exactly fraction of measured UDP payload C0; inferred DDS app cap uses provisional header factor'
        if label=='bp_default100':cfg['fq_flow_limit']=100
        if label=='vendor':cfg.update(socket_tx_bytes=1048576,socket_rx_bytes=4194304 if rmw=='fastdds' else 10485760)
        folders={h:home+'/'+REMOTE+'/runs/'+self.a.run+'/'+self.out.name+'/'+name for h,home in self.homes.items()}
        old={};pids={};last_guard=time.monotonic()
        print('START '+name,flush=True)
        try:
            for h in self.homes:
                old[h]=self.c.python(h,"import json,subprocess;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n','net.core.'+k],text=True)) for k in ['rmem_max','wmem_max']}))")
                self.write(h,folders[h]+'/config.json',json.dumps(cfg,indent=2).encode())
                if label!='default' or rmw=='cyclonedds':
                    profile=local/('profile'+h+'.xml');self.profile(rmw,label,h,cfg,profile);self.write(h,folders[h]+'/middleware.xml',profile.read_bytes())
                    q=self.c.extra(h,'sudo -n sysctl -w net.core.rmem_max='+str(max(old[h]['rmem_max'],cfg['socket_rx_bytes']))+' net.core.wmem_max='+str(max(old[h]['wmem_max'],cfg['socket_tx_bytes'])))
                    if q.returncode:raise RuntimeError(q.stderr.decode())
                for k,args in [
                    ('wireguard',['sudo','-n','timeout','-k','2','64','python3','tools/w1_wired_guard.py','--seconds','57','--out',folders[h]+'/wired_guard.json']),
                    ('clock',['sudo','-n','timeout','-k','2','59','python3','tools/w1_clock_sample.py','--seconds','53','--out',folders[h]+'/clock.jsonl']),
                    ('telemetry',['sudo','-n','timeout','-k','2','59','python3','tools/telemetry.py','--seconds','53','--interval','.1','--dev','wlp2s0','--out',folders[h]+'/telemetry.jsonl'])]:
                    pids[k+h]=self.launch(h,args,folders[h],k+'.log')
                    if k=='wireguard':last_guard=time.monotonic()
            time.sleep(.5)
            if label=='fixed' or self.a.backpressure:
                pids['govern']=self.launch('4',['sudo','-n','timeout','-k','2','50','python3','-m','rospacer','govern','--config',folders['4']+'/config.json','--mode','fixed','--seconds','46','--trace',folders['4']+'/govern.csv'],folders['4'],'govern.log')
                time.sleep(.5)
            for h in self.homes:
                pids['capture'+h]=self.launch(h,['sudo','-n','timeout','-s','INT','-k','2','40','tcpdump','-i','wlp2s0','-s','160','-w',folders[h]+'/wifi.pcap','not','port','22','and','not','port','123'],folders[h],'capture.log')
            env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=74 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
            def command(h,role):
                e=env
                if self.a.pinned:e+='export LD_LIBRARY_PATH='+self.homes[h]+'/'+REMOTE+'/runtime_w1_45/'+rmw+':$LD_LIBRARY_PATH; '
                if label!='default' or rmw=='cyclonedds':e+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+folders[h]+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+folders[h]+'/middleware.xml; ')
                if label=='vendor' and rmw=='fastdds':e+='export FASTDDS_BUILTIN_TRANSPORTS=LARGE_DATA RMW_FASTRTPS_USE_QOS_FROM_XML=0; '
                args=['timeout','-k','2','44','python3','tools/traffic.py',role,'--seconds',str(duration if role=='pub' else 38),'--hz',str(hz),'--count',str(count),'--out',folders[h]+'/'+role+'.json']
                if role=='pub':args+=['--discovery-seconds','8','--drain-seconds','5','--continue-on-publish-error']
                return e+'cd '+self.homes[h]+'/'+REMOTE+'; exec '+shlex.join(args)
            pids['sub']=self.launch('5',['bash','-c',command('5','sub')],folders['5'],'sub.log');time.sleep(.7)
            pids['pub']=self.launch('4',['bash','-c',command('4','pub')],folders['4'],'pub.log')
            while time.monotonic()-last_guard<60:time.sleep(min(1,60-(time.monotonic()-last_guard)))
            for h in self.homes:self.archive(h,folders[h],local/h)
            pub=json.loads((local/'4/pub.json').read_text());sub=json.loads((local/'5/sub.json').read_text())
            library_check={}
            if self.a.pinned:
                expected=json.loads((ROOT/'runs'/self.a.run/'runtime/manifest.json').read_text())[rmw]['manifest']
                for h,role in [('4','pub'),('5','sub')]:
                    actual=json.loads((local/h/(role+'.metadata.json')).read_text())['libraries']
                    valid=bool(actual) and all('/runtime_w1_45/'+rmw+'/' in path and expected.get(Path(path).name)==digest for path,digest in actual.items())
                    library_check[h]={'valid':valid,'libraries':actual}
                    if not valid:raise RuntimeError('actual loaded DDS/RMW closure differs from frozen manifest')
            stamps=[r[k] for r in sub.get('records',[]) for k in ['publisher_wall_ns','arrival_wall_ns'] if k in r]
            clock=qualify_pair(*[[json.loads(s) for s in (local/h/'clock.jsonl').read_text().splitlines()] for h in ['4','5']],min(stamps) if stamps else 0,max(stamps) if stamps else 0)
            summary={'name':name,'config':cfg,'commit':self.commit,'source_sha256':self.hashes,'requested_hz':hz,'clock':clock,'metrics':analyze_pair(pub,sub,clock),'telemetry':{h:analyze_telemetry(local/h/'telemetry.jsonl') for h in self.homes},'pids':pids,'duration_s':duration,'comparison_scope':'short functional smoke; no performance superiority claim; wired DDS rejected while clocks/SSH allowed'}
            summary['pinned_runtime_check']=library_check
            summary['restoration']={h:json.loads((local/h/'wired_guard.restoration.json').read_text()) for h in self.homes}
            summary['qdisc_after']=self.c.python('4',"import subprocess,json;print(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0'],text=True))")
            (local/'summary.json').write_text(json.dumps(summary,indent=2))
            print(json.dumps({'DONE':name,'received':summary['metrics']['unique_received'],'requested':count,'clock_validated':clock['validated'],'bound_ms':clock.get('relative_error_bound_ms'),'p95_ms':(summary['metrics']['end_to_end_latency_ms'] or {}).get('p95')}),flush=True)
        finally:
            for h,vals in old.items():
                q=self.c.extra(h,'sudo -n sysctl -w '+shlex.join(['net.core.'+k+'='+str(v) for k,v in vals.items()]))
                if q.returncode:raise RuntimeError('buffer restoration failed '+q.stderr.decode())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--ip4',default='192.168.0.4');p.add_argument('--ip5',default='192.168.0.5');p.add_argument('--seconds',type=float,default=15);p.add_argument('--middleware',choices=['fastdds','cyclonedds']);p.add_argument('--label',choices=['default','vendor','static','fixed']);p.add_argument('--pinned',action='store_true');p.add_argument('--backpressure',action='store_true');a=p.parse_args()
    if a.backpressure:a.seconds=30
    if Path(a.run).name!=a.run or (not a.backpressure and not 5<=a.seconds<=20):p.error('single run folder and smoke duration5..20s')
    c=Campaign(a)
    try:
        c.c.connect(OTHER);c.deploy()
        for rmw in [a.middleware] if a.middleware else ['fastdds','cyclonedds']:
            for label in ['bp_default100','bp_design'] if a.backpressure else [a.label] if a.label else ['default','vendor','static','fixed']:c.trial(rmw,label)
    finally:c.c.connect(SR2)


if __name__=='__main__':main()
