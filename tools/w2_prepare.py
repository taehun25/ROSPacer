"""Deploy a frozen offline runtime and finite W2 guards without upgrading ROS."""
import io,json,tarfile,hashlib,shlex,time,sys
from pathlib import Path
from deploy import ROOT
from w2_control import Lab,inventory,HOSTS,OTHER,SR2
BASE=ROOT/'runs/w2_20261014_3rep'

def main():
    lab=Lab(BASE);r={}
    for ap,hs in [(OTHER,['4','5']),(SR2,['12','10'])]:
        lab.select(ap)
        for h in hs:
            inv=inventory(lab,h)
            if inv['experiments']['rc']!=1:raise RuntimeError('existing experiment '+h)
            home=lab.home(h);dest=home+'/runs/'+BASE.name
            lab.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
            r[h]=lab.py(h,'import json,subprocess;print(json.dumps(json.loads(subprocess.check_output('+repr(['sudo','-n','python3',home+'/tools/w2_host_guard.py','begin','--folder',dest+'/session','--host',h])+',text=True))))')
            print(json.dumps({'prepared_host':h,**r[h]}),flush=True)
            (BASE/'sessions.json').write_text(json.dumps(r,indent=2))
    lab.select(OTHER);lab.wired=True
    # Preserve binaries exactly; the same W1 runtime closure is used everywhere.
    blob=lab.ssh('4',"tar -czf - -C "+shlex.quote(lab.home('4'))+" runtime_w1_45",timeout=60)
    (BASE/'runtime_w1_45.tar.gz').write_bytes(blob)
    manifests={}
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tf:
        for m in tf:
            if m.isfile():manifests[m.name]=hashlib.sha256(tf.extractfile(m).read()).hexdigest()
    (BASE/'runtime_manifest.json').write_text(json.dumps(manifests,indent=2))
    for ap,hs in [(OTHER,['5']),(SR2,['12','10'])]:
        lab.select(ap)
        for h in hs:
            home=lab.home(h);target=home+'/runtime_w2'
            code='import sys,tarfile;from pathlib import Path;p=Path('+repr(target)+');p.mkdir(exist_ok=True)\nwith tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as tf:\n for m in tf:\n  pp=Path(m.name)\n  if ".." in pp.parts or pp.parts[0]!="runtime_w1_45":raise ValueError("member")\n  if m.isfile():\n   f=p/Path(*pp.parts[1:]);f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(tf.extractfile(m).read())'
            lab.ssh(h,'python3 -c '+shlex.quote(code),blob,timeout=80)
    lab.select(OTHER)
    # Root preparation doesn't carry application data over the management wire.
    clock={}
    for h in ['4','5']:
        clock[h]=lab.py(h,'import json,subprocess;print(json.dumps({k:subprocess.check_output(v,text=True,timeout=8) for k,v in '+repr({'clock':['chronyc','-n','tracking'],'sources':['chronyc','-n','sources'],'ntp':['chronyc','-n','ntpdata']})+'.items()}))')
    (BASE/'clock_initial.json').write_text(json.dumps(clock,indent=2));print(json.dumps(clock),flush=True)
    (BASE/'preparation_ready.json').write_text(json.dumps({'sessions':r,'runtime_sha256':hashlib.sha256(blob).hexdigest(),'wall':time.time()}))

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
