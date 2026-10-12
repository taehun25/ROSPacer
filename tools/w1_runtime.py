"""Freeze host10's Fast DDS/RMW ROS shared-library closure without system upgrades."""
import hashlib,json,tarfile,io
from pathlib import Path
from deploy import ROOT,REMOTE,ssh

def main():
    source=r'''
import subprocess,os,re,tarfile,sys
from pathlib import Path
env=dict(os.environ,LD_LIBRARY_PATH='/opt/ros/humble/lib')
todo=[Path('/opt/ros/humble/lib/librmw_fastrtps_cpp.so')];seen=set()
while todo:
 p=todo.pop()
 if p in seen:continue
 seen.add(p)
 q=subprocess.run(['ldd',str(p)],env=env,capture_output=True,text=True,check=True)
 if 'not found' in q.stdout:raise RuntimeError(q.stdout)
 for path in re.findall(r'=>\s+(/opt/ros/humble/lib/\S+)',q.stdout):
  if Path(path) not in seen:todo.append(Path(path))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',dereference=True) as tf:
 for p in sorted(seen):tf.add(p,arcname=p.name)
'''
    q=ssh('10','python3 -',source.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    archive=ROOT/'runs'/'w1_20261012_163000'/'runtime_fastdds_from10.tar.gz'
    archive.parent.mkdir(parents=True,exist_ok=True);archive.write_bytes(q.stdout)
    manifest={}
    with tarfile.open(fileobj=io.BytesIO(q.stdout),mode='r:gz') as tf:
        for item in tf:
            manifest[item.name]=hashlib.sha256(tf.extractfile(item).read()).hexdigest()
    for host,home in [('12','/home/csi2'),('10','/home/csi')]:
        dest=home+'/'+REMOTE+'/runtime_fastdds_w1'
        code="import sys,tarfile,pathlib,json,hashlib; p=pathlib.Path("+repr(dest)+");p.mkdir(parents=True,exist_ok=True); t=tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz'); "
        code+="\nfor member in t:\n if '/' in member.name or not member.isfile():raise RuntimeError('unexpected archive path')\n (p/member.name).write_bytes(t.extractfile(member).read())\n"
        code+="print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file()}))"
        import shlex
        r=ssh(host,'python3 -c '+shlex.quote(code),q.stdout)
        if r.returncode:raise RuntimeError(r.stderr.decode())
        if json.loads(r.stdout)!=manifest:raise RuntimeError('runtime hash mismatch')
    (archive.parent/'runtime_manifest.json').write_text(json.dumps({'origin_host':'10','origin_prefix':'/opt/ros/humble/lib','manifest':manifest,
      'Fast_DDS_version':'2.6.11','RMW_fastrtps_version':'6.2.10','Fast_CDR_version':'1.0.29',
      'scope':'Identical copied DDS/RMW ROS-library closure selected only by W1 LD_LIBRARY_PATH; system packages unchanged; node maps still must verify actual loading'},indent=2))
    print(json.dumps({'files':len(manifest),'bytes':len(q.stdout),'manifest':manifest}))

if __name__=='__main__':main()
