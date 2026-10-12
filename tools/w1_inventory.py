"""Read-only W1 environment inventory on the verified SR2 pair."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from deploy import ssh, ROOT

SOURCE = r'''
import subprocess,json,os
from pathlib import Path
dev=DEV
commands={
 'identity':['hostnamectl'], 'hardware':['lspci','-nnk'],
 'usb':['lsusb'], 'interfaces':['ip','-j','addr'],
 'routes':['ip','-j','route'], 'power_save':['iw','dev',dev,'get','power_save'],
 'driver':['ethtool','-i',dev], 'clock':['chronyc','tracking'],
 'clock_sources':['chronyc','sources','-v'],
 'chrony_config':['cat','/etc/chrony/chrony.conf'],
 'packages':['dpkg-query','-W','ros-humble-fastrtps','ros-humble-rmw-fastrtps-cpp','ros-humble-rmw-cyclonedds-cpp','ros-humble-cyclonedds','iproute2','iperf3','chrony'],
 'fastdds_available':['apt-cache','policy','ros-humble-fastrtps','ros-humble-rmw-fastrtps-cpp'],
 'all_processes':['ps','-eo','pid,comm,args'],
 'root_survey':['sudo','-n','iw','dev',dev,'survey','dump'],
 'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],
 'network_profile':['nmcli','-f','GENERAL.CONNECTION,GENERAL.HWADDR','device','show',dev],
 'root_access':['sudo','-n','true'],
}
report={'utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'dev':dev}
for k,v in commands.items():
 try:
  q=subprocess.run(v,capture_output=True,text=True,timeout=12)
  report[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
 except Exception as e: report[k]={'error':str(e)}
report['sysfs_driver']=str(Path('/sys/class/net/'+dev+'/device/driver').resolve())
print(json.dumps(report))
'''

def main():
    folder=ROOT/'runs'/datetime.now(timezone.utc).strftime('w1_inventory_%Y%m%d_%H%M%S')
    folder.mkdir(parents=True)
    def one(host):
        dev={'12':'wlo1','10':'wlp2s0'}[host]
        q=ssh(host,'python3 -',('DEV='+repr(dev)+'\n'+SOURCE).encode())
        if q.returncode: raise RuntimeError(q.stderr.decode())
        report=json.loads(q.stdout)
        (folder/(host+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        return host,report
    with ThreadPoolExecutor(2) as pool:
        reports=dict(pool.map(one,['12','10']))
    print(json.dumps({'folder':str(folder),'hosts':{h:{k:r[k] for k in ('identity','interfaces','power_save','clock','clock_sources','packages','fastdds_available','root_access','root_survey')} for h,r in reports.items()}},indent=2))

if __name__=='__main__':main()
