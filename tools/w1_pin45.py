"""Freeze isolated DDS/RMW closures without touching research installations."""
import hashlib
import io
import json
import shlex
import tarfile
from deploy import ROOT,REMOTE
from w1_b2 import Control,OTHER,SR2


def prepare(c,out):
    fast=(ROOT/'runs/w1_20261012_163000/runtime_fastdds_from10.tar.gz').read_bytes()
    expected=json.loads((ROOT/'runs/w1_20261012_163000/runtime_manifest.json').read_text())['manifest']
    source=r'''import subprocess,tarfile,sys,os,re
from pathlib import Path
prefix=Path.home()/'ros2_ws/install'
env=dict(os.environ,LD_LIBRARY_PATH=':'.join(str(p) for p in prefix.glob('*/lib'))+':/opt/ros/humble/lib:/opt/ros/humble/lib/x86_64-linux-gnu')
todo=[prefix/'rmw_cyclonedds_cpp/lib/librmw_cyclonedds_cpp.so',prefix/'cyclonedds/lib/libddsc.so.0'];seen=set()
while todo:
 p=todo.pop()
 if p in seen:continue
 seen.add(p);q=subprocess.run(['ldd',str(p)],env=env,capture_output=True,text=True,check=True)
 if 'not found' in q.stdout:raise RuntimeError(q.stdout)
 for name in re.findall(r'=>\s+(/\S+)',q.stdout):
  f=Path(name)
  if (str(f).startswith(str(prefix)) or str(f).startswith('/opt/ros/humble/lib/')) and f not in seen:todo.append(f)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',dereference=True) as tf:
 for f in sorted(seen):tf.add(f,arcname=f.name)
'''
    q=c.extra('4','python3 -',source.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    cyclone=q.stdout;(out/'cyclone_clean_from4.tar.gz').write_bytes(cyclone)
    manifests={}
    for vendor,data in [('fastdds',fast),('cyclonedds',cyclone)]:
        manifest={}
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tf:
            for m in tf:
                if '/' in m.name or not m.isfile():raise RuntimeError('invalid closure member')
                manifest[m.name]=hashlib.sha256(tf.extractfile(m).read()).hexdigest()
        if vendor=='fastdds' and manifest!=expected:raise RuntimeError('previous stock closure hash mismatch')
        for h,home in [('4','/home/csilab'),('5','/home/csi')]:
            dest=home+'/'+REMOTE+'/runtime_w1_45/'+vendor
            script='import sys,tarfile,json,hashlib;from pathlib import Path\np=Path('+repr(dest)+');p.mkdir(parents=True,exist_ok=True)\nwith tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as tf:\n for m in tf:\n  if "/" in m.name or not m.isfile():raise RuntimeError("invalid closure")\n  (p/m.name).write_bytes(tf.extractfile(m).read())\nprint(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file()}))'
            q=c.extra(h,'python3 -c '+shlex.quote(script),data)
            if q.returncode or json.loads(q.stdout)!=manifest:raise RuntimeError('runtime deployment mismatch')
        manifests[vendor]={'manifest':manifest,'origin':'stock Ubuntu ROS packages from host10' if vendor=='fastdds' else 'clean source workspace host4: Cyclone2cdd114c, RMWfa8831b9; clean Git status','scope':'isolated LD_LIBRARY_PATH closure; actual maps hashes required'}
    (out/'manifest.json').write_text(json.dumps(manifests,indent=2));print(json.dumps({k:len(v['manifest']) for k,v in manifests.items()}))


def main():
    out=ROOT/'runs/w1_20261012_radio45/runtime';out.mkdir(parents=True,exist_ok=True)
    c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',out)
    try:
        c.connect(OTHER);prepare(c,out)
    finally:c.connect(SR2)


if __name__=='__main__':main()
