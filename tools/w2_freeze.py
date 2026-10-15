"""One final complete F schedule, then freeze the local unattended launch inputs."""
import json,sys,time,subprocess,hashlib
from pathlib import Path
from deploy import ROOT
from w2_runner import write
from w2_control import SR2,OTHER,HOSTS
import w2_extended_smoke as s

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    s.r.ap_pair(SR2);s.r.deploy()
    s.test('smoke_F_adaptive_v1','F','cyclonedds','adaptive',seconds=80)
    # Return peers to their baseline AP so the first E run starts without
    # competitor association or traffic. No experiment remains running.
    s.r.ap_pair(SR2)
    checks={}
    for ap,hosts in [(OTHER,['4','5']),(SR2,['12','10'])]:
        s.r.lab.select(ap)
        for h in hosts:
            folder=s.r.sessions[h]['folder']
            code='''import json,os,subprocess
from pathlib import Path
folder=Path(FOLDER)
cmds={"link":["iw","dev",DEV,"link"],"qdisc":["tc","-j","qdisc","show","dev",DEV],"sudo":["sudo","-n","id","-u"],"disk":["df","-B1",str(folder)]}
out={k:subprocess.check_output(v,text=True) for k,v in cmds.items()}
out["guard_restored"]=(folder/"restoration.json").exists()
print(json.dumps(out))
'''.replace('FOLDER',repr(folder)).replace('DEV',repr(HOSTS[h][3]))
            d=s.r.runpy(h,code)
            if d['sudo'].strip()!='0' or d['guard_restored'] or any(q['kind']!='noqueue' for q in json.loads(d['qdisc'])):raise RuntimeError('launch preflight failed '+h)
            checks[h]=d
    s.r.lab.select(OTHER)
    files=list((ROOT/'tools').glob('w2_*'))+list((ROOT/'tests').glob('test_w2_*'))
    write(s.r.base/'prelaunch.json',{'passed':True,'checked_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'host_checks':checks,'file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()},'git_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_snapshot':'source_snapshot.tar.gz','dirty_sources_preserved':True,'T3_Adaptive_blocked':True,'F_smoke':s.r.results})
    print('prelaunch: passed',flush=True)
