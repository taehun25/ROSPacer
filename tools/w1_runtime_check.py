"""Create endpoints without sending data; verify live loaded DDS/RMW libraries."""
import json,shlex
from pathlib import Path
from deploy import ROOT,REMOTE,ssh

CODE=r'''
import rclpy,json,hashlib,os
from pathlib import Path
from std_msgs.msg import UInt8MultiArray
from rclpy.qos import QoSProfile,ReliabilityPolicy,HistoryPolicy
rclpy.init();n=rclpy.create_node('w1_runtime_probe')
p=n.create_publisher(UInt8MultiArray,'/w1_runtime_probe',QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,history=HistoryPolicy.KEEP_ALL))
libs=sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if line.split()[-1].startswith('/') and any(k in line for k in ['libfastrtps','libfastcdr','librmw_fastrtps','libddsc','librmw_cyclonedds'])})
print(json.dumps({'rmw':os.environ.get('RMW_IMPLEMENTATION'),'libraries':{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in libs},'qos':str(p.qos_profile)}))
n.destroy_node();rclpy.shutdown()
'''

def main():
    results={}
    for h,home in [('12','/home/csi2'),('10','/home/csi')]:
        results[h]={}
        for rmw in ['rmw_fastrtps_cpp','rmw_cyclonedds_cpp']:
            script='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=73 RMW_IMPLEMENTATION='+rmw+'; '
            if rmw=='rmw_fastrtps_cpp':script+='export LD_LIBRARY_PATH='+home+'/'+REMOTE+'/runtime_fastdds_w1:$LD_LIBRARY_PATH; '
            script+='unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML; python3 -c '+shlex.quote(CODE)
            q=ssh(h,'bash -c '+shlex.quote(script))
            results[h][rmw]={'rc':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}
    folder=ROOT/'runs'/'w1_20261012_163000';(folder/'runtime_check.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
