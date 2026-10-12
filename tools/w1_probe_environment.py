import json,subprocess
from pathlib import Path
out={}
for key,args in {
 'ldd_fast':['ldd','/opt/ros/humble/lib/librmw_fastrtps_cpp.so'],
 'fastcdr':['dpkg-query','-W','ros-humble-fastcdr','ros-humble-rmw-fastrtps-shared-cpp','ros-humble-rosidl-typesupport-fastrtps-cpp'],
 'chrony_files':['find','/etc/chrony','-maxdepth','2','-type','f'],
 'chrony_services':['systemctl','is-active','chrony'],
 'sysinfo':['bash','-c','find ~/ros2_ws/src -maxdepth 3 -name .git -type d'],
 'cpu_governor':['bash','-c','cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'],
 'ntp_sockets':['ss','-ulpn'],
}.items():
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=8)
  out[key]={'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except Exception as e:out[key]={'error':str(e)}
out['chrony_conf']=Path('/etc/chrony/chrony.conf').read_text()
out['source_files']={str(p):p.read_text() for p in Path('/etc/chrony').rglob('*.sources')}
print(json.dumps(out,indent=2))
