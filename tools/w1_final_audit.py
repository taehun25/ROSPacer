"""Final read-only state/source audit plus bounded golden node parser checks."""
import json,shlex,sys
from pathlib import Path
from deploy import ROOT,REMOTE,ssh
from w1_calibrate import remote
from w1_backpressure import setup,shell,write_remote
sys.path.insert(0,str(ROOT))
from rospacer.model import golden_profile
from rospacer import profiles

def main():
    base=ROOT/'runs/w1_20261012_163000';result={}
    for h,home,dev,ip,peer in [('12','/home/csi2','wlo1','192.168.0.3','192.168.0.4'),('10','/home/csi','wlp2s0','192.168.0.4','192.168.0.3')]:
        source=r'''
import subprocess,json,time,os
from pathlib import Path
commands={
 'qdisc':['tc','-j','-s','qdisc','show','dev',DEV],
 'power':['iw','dev',DEV,'get','power_save'],
 'clock':['chronyc','tracking'],
 'processes':['pgrep','-af',r'[t]raffic.py|[r]ospacer govern|[i]perf3|[w]1_session.py|[w]1_outage.py|[w]1_wifi_shaper'],
 'cpu':['cat','/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'],
 'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],
 'Cyclone_commit':['git','-C',str(Path.home()/'ros2_ws/src/CycloneDDS'),'rev-parse','HEAD'],
 'Cyclone_dirty':['git','-C',str(Path.home()/'ros2_ws/src/CycloneDDS'),'status','--porcelain'],
 'RMW_Cyclone_commit':['git','-C',str(Path.home()/'ros2_ws/src/rmw_cyclonedds'),'rev-parse','HEAD'],
}
r={'wall_ns':time.time_ns(),'dev':DEV}
for k,v in commands.items():
 try:
  p=subprocess.run(v,capture_output=True,text=True,timeout=3);r[k]={'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except Exception as e:r[k]={'error':str(e)}
print(json.dumps(r))
'''
        result[h]=remote(h,'DEV='+repr(dev)+'\n'+source)
        result[h]['golden_live']={}
        originals={k:int(shell(h,'cat /proc/sys/net/core/'+k)['stdout']) for k in ['rmem_max','wmem_max']}
        try:
            shell(h,'sudo -n /sbin/sysctl -w net.core.rmem_max=1048576')
            for rmw in ['fastdds','cyclonedds']:
                cfg=golden_profile();path=base/('golden_'+rmw)/('live_'+h+'.xml')
                if rmw=='fastdds':profiles.fastdds(cfg,path,ip)
                else:profiles.cyclone(cfg,path,dev,peer)
                profiles.validate(path,ROOT/'reference'/('fastdds-2.6.10-local-validation.xsd' if rmw=='fastdds' else 'cyclonedds-0.10.5.xsd'))
                dest=home+'/'+REMOTE+'/runs/w1_20261012_163000/golden_'+rmw+'/live.xml';write_remote(h,dest,path.read_text())
                env=setup(rmw,h)
                env+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+dest+' RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+dest+'; ')
                code='import rclpy,json;from std_msgs.msg import UInt8MultiArray;from rclpy.qos import QoSProfile,ReliabilityPolicy,HistoryPolicy;rclpy.init();n=rclpy.create_node("w1_golden_parser");p=n.create_publisher(UInt8MultiArray,"/w1_golden_parser",QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,history=HistoryPolicy.KEEP_ALL));print(json.dumps({"node_created":True,"qos":str(p.qos_profile)}));n.destroy_node();rclpy.shutdown()'
                result[h]['golden_live'][rmw]=shell(h,env+'timeout -k 2 8 python3 -c '+shlex.quote(code),False)
        finally:
            shell(h,'sudo -n /sbin/sysctl -w net.core.rmem_max='+str(originals['rmem_max'])+' net.core.wmem_max='+str(originals['wmem_max']))
        result[h]['buffers_restored_after_golden']={k:int(shell(h,'cat /proc/sys/net/core/'+k)['stdout']) for k in originals}==originals
    (base/'final_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({h:{'processes':r['processes'],'Cyclone_commit':r['Cyclone_commit'],'RMW_Cyclone_commit':r['RMW_Cyclone_commit'],'golden':{mw:v['rc'] for mw,v in r['golden_live'].items()},'buffers_restored':r['buffers_restored_after_golden']} for h,r in result.items()},indent=2))

if __name__=='__main__':main()
