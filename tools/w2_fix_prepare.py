import json,sys,shlex,subprocess,time
from deploy import ROOT
from w2_control import Lab,OTHER,SR2
BASE=ROOT/'runs/w2_20261014_3rep'
lab=Lab(BASE);sessions=json.loads((BASE/'sessions.json').read_text())
for ap,hs in [(OTHER,['4','5']),(SR2,['12','10'])]:
    lab.select(ap)
    for h in hs:
        home=lab.home(h);script=home+'/tools/w2_host_guard.py'
        lab.put(h,script,(ROOT/'tools/w2_host_guard.py').read_bytes())
        if h in ['12','10']:
            z=lab.ssh(h,shlex.join(['python3',script,'end','--folder',home+'/runs/'+BASE.name+'/session','--host',h]),root=True,timeout=60)
            f=home+'/runs/'+BASE.name+'/session_v2'
            z=lab.ssh(h,shlex.join(['python3',script,'begin','--folder',f,'--host',h]),root=True,timeout=60)
            sessions[h]=json.loads(z);sessions[h]['folder']=f
        else:sessions[h]['folder']=home+'/runs/'+BASE.name+'/session'
        (BASE/'sessions.json').write_text(json.dumps(sessions,indent=2));print('guard ready '+h,flush=True)
lab.select(OTHER);lab.wired=True
code='''import subprocess,json\nr={}\nfor k,a in {'tracking':['chronyc','-n','tracking'],'sources':['chronyc','-n','sources'],'ntp':['chronyc','-n','ntpdata'],'process':['pgrep','-a','chronyd'],'service':['systemctl','show','chrony','-p','ExecStart'],'ether':['ip','-j','address','show','dev','enp1s0']}.items():\n q=subprocess.run(a,capture_output=True,text=True,timeout=8);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nprint(json.dumps(r))'''
r={h:lab.py(h,code) for h in ['4','5']}
(BASE/'clock_diagnosis.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
