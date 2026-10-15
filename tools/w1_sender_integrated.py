"""Bootstrap/collect only: calibration and fitting execute on sender4.

No management Ethernet address is added. Receiver gets only an ordinary SSH
authorized public key restricted to iw and bounded iperf3; no code deployment.
"""
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
from deploy import ROOT, REMOTE
from w1_sender_validation_finish import IPv6Control
from w1_ros45 import Campaign

BASE = ROOT/'runs/w1_20261014_sender_integrated'
HOME = '/home/csilab/'+REMOTE
REMOTE_BASE = HOME+'/runs/'+BASE.name
BUNDLE = 'calibration_controlled'
VALIDATIONS = ['validation_clean_controlled', 'validation_B2_controlled', 'validation_C2_controlled_r1']


def control():
    return IPv6Control('192.168.0.4', '192.168.0.5', 'Wi-Fi 2', BASE)


def prepare():
    BASE.mkdir(exist_ok=False)
    c = control(); cam = object.__new__(Campaign); cam.c = c; cam.homes = {'4': '/home/csilab', '5': '/home/csi'}
    baseline = {}
    for h in ('4', '5'):
        baseline[h] = c.python(h, "import json,subprocess;from pathlib import Path;r={};\nfor k,a in {'link':['iw','dev','wlp2s0','link'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'addresses':['ip','-j','addr'],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],'processes':['ps','-eo','args']}.items():r[k]=subprocess.check_output(a,text=True)\nprint(json.dumps(r))")
        if 'SSID: iptime5GAX1500\n' not in baseline[h]['link'] or not all(q['kind'] == 'noqueue' for q in json.loads(baseline[h]['qdisc'])):
            raise RuntimeError('lab scope changed')
        if any(x in baseline[h]['processes'] for x in ['iperf3 -c', 'iperf3 -s', 'tools/traffic.py', ' -m rospacer sender-govern']):
            raise RuntimeError('existing experiment must be preserved')
    (BASE/'baseline.json').write_text(json.dumps(baseline, indent=2))
    # Sender-only package deployment. Receiver remains untouched except SSH key.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        for f in (ROOT/'rospacer').glob('*.py'): tf.add(f, arcname='rospacer/'+f.name)
    code = "import sys,tarfile;from pathlib import Path\np=Path("+repr(HOME)+")\nwith tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as tf:\n for m in tf:\n  if not m.isfile() or Path(m.name).parts[0]!='rospacer' or len(Path(m.name).parts)!=2:raise ValueError('member')\n  (p/m.name).write_bytes(tf.extractfile(m).read())"
    q = c.extra('4', 'python3 -c '+shlex.quote(code), buf.getvalue()); assert q.returncode == 0, q.stderr
    for name in ['tools/w1_session.py']:
        cam.write('4', HOME+'/'+name, (ROOT/name).read_bytes())
    # Create a dedicated key on sender. Never copy its private key to the PC.
    q = c.extra('4', 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && test ! -e ~/.ssh/id_ed25519_rospacer_cal && ssh-keygen -q -t ed25519 -N "" -C ROSPacer-sender-calibration -f ~/.ssh/id_ed25519_rospacer_cal')
    if q.returncode:
        q = c.extra('4', 'test -f ~/.ssh/id_ed25519_rospacer_cal.pub'); assert q.returncode == 0
    q = c.extra('4', 'cat ~/.ssh/id_ed25519_rospacer_cal.pub'); assert q.returncode == 0
    public = q.stdout.decode().strip()
    commands = ['iw dev wlp2s0 link', 'iw dev wlp2s0 info', 'cat /proc/net/snmp', 'ss -H -lnt']
    commands += [f'timeout -k 2 {s} iperf3 -s -1 -B 192.168.0.5 -p 55946 -J -i .2' for s in range(25, 61)]
    forced = 'case "$SSH_ORIGINAL_COMMAND" in '+ '|'.join(shlex.quote(s) for s in commands)+') exec sh -c "$SSH_ORIGINAL_COMMAND" ;; *) exit 126 ;; esac'
    authorized = 'restrict,command="'+forced.replace('\\', '\\\\').replace('"', '\\"')+'" '+public
    r = c.python('5', "import json;from pathlib import Path;p=Path.home()/'.ssh';p.mkdir(exist_ok=True);p.chmod(0o700);f=p/'authorized_keys';s=f.read_text() if f.exists() else '';line="+repr(authorized)+";key="+repr(public.split()[1])+";\nif key not in s:f.write_text(s.rstrip()+'\\n'+line+'\\n')\nf.chmod(0o600);print(json.dumps({'restricted_key_ready':True}))")
    known = subprocess.check_output(['ssh-keygen', '-F', '192.168.0.5'], text=True)
    known = '\n'.join(line for line in known.splitlines() if not line.startswith('#'))+'\n'
    cam.write('4', '/home/csilab/.ssh/rospacer_cal_known_hosts', known.encode())
    q = c.extra('4', 'ssh -6 -o BatchMode=yes -o StrictHostKeyChecking=yes -o HostKeyAlias=192.168.0.5 -o UserKnownHostsFile=/home/csilab/.ssh/rospacer_cal_known_hosts -i /home/csilab/.ssh/id_ed25519_rospacer_cal csi@fe80::4f91:cec0:78f5:cc75%wlp2s0 "iw dev wlp2s0 link"')
    assert q.returncode == 0, q.stderr
    # Sender-only finite power/buffer recovery. No wired address is introduced.
    c.python('4',"from pathlib import Path;p=Path("+repr(REMOTE_BASE)+");p.mkdir(parents=True,exist_ok=True);print('{}')")
    q = c.extra('4', shlex.join(['sudo', '-n', 'python3', HOME+'/tools/w1_session.py', 'begin', '--folder', REMOTE_BASE+'/perf', '--dev', 'wlp2s0', '--expiry-seconds', '21600']))
    assert q.returncode == 0, q.stderr
    (BASE/'session.json').write_bytes(q.stdout)
    (BASE/'deployment.json').write_text(json.dumps({'sender_package_only': True, 'receiver_new_program': False, 'management_ethernet_added': False, 'receiver_ssh_scope': commands, 'restricted_public_key': public, 'profile_computation_location': 'sender4'}, indent=2))


def common():
    return ['--dev', 'wlp2s0', '--source', '192.168.0.4', '--peer', '192.168.0.5',
            '--peer-ssh', 'csi@fe80::4f91:cec0:78f5:cc75%wlp2s0', '--ssh-key', '/home/csilab/.ssh/id_ed25519_rospacer_cal',
            '--known-hosts', '/home/csilab/.ssh/rospacer_cal_known_hosts', '--host-key-alias', '192.168.0.5', '--seconds', '15', '--socket-bytes', '1048576']


def setup_bench():
    c=control();cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab','5':'/home/csi'}
    q=c.extra('4','test -e ~/.ssh/id_ed25519_rospacer_w1bench || ssh-keygen -q -t ed25519 -N "" -C ROSPacer-W1-benchmark-only -f ~/.ssh/id_ed25519_rospacer_w1bench')
    assert q.returncode==0,q.stderr
    q=c.extra('4','cat ~/.ssh/id_ed25519_rospacer_w1bench.pub');assert q.returncode==0
    pub=q.stdout.decode().strip()
    c.python('5',"from pathlib import Path;import json;f=Path.home()/'.ssh/authorized_keys';s=f.read_text();line="+repr('restrict '+pub)+";key="+repr(pub.split()[1])+";\nif key not in s:f.write_text(s.rstrip()+'\\n'+line+'\\n')\nprint('{}')")
    (BASE/'benchmark_public_key.txt').write_text(pub)
    cam.write('4',HOME+'/tools/w1_sender_local_smoke.py',(ROOT/'tools/w1_sender_local_smoke.py').read_bytes())
    # These two finite settings are benchmark preparation, not online feedback.
    q=c.extra('5','sudo -n python3 /home/csi/'+REMOTE+'/tools/w1_session.py begin --folder /home/csi/'+REMOTE+'/runs/'+BASE.name+'/perf --dev wlp2s0 --expiry-seconds 21600');assert q.returncode==0,q.stderr
    (BASE/'session5.json').write_bytes(q.stdout)
    q=c.extra('5','sudo -n chown csi:csi /home/csi/'+REMOTE+'/runs/'+BASE.name);assert q.returncode==0,q.stderr
    q=c.extra('4','sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0,q.stderr
    q=c.extra('5','sudo -n sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304');assert q.returncode==0,q.stderr


def smoke(tag,rmw,condition,mode=None,reps=2):
    c=control()
    cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab'}
    cam.write('4',HOME+'/tools/w1_sender_local_smoke.py',(ROOT/'tools/w1_sender_local_smoke.py').read_bytes())
    q=c.extra('4','python3 '+HOME+'/tools/w1_sender_local_smoke.py --help');assert q.returncode==0,q.stderr
    args=['sudo','-n','python3','tools/w1_sender_local_smoke.py','--bundle',REMOTE_BASE+'/'+BUNDLE,'--out',REMOTE_BASE+'/'+tag,
          '--rmw',rmw,'--condition',condition,'--key','/home/csilab/.ssh/id_ed25519_rospacer_w1bench','--seconds','15','--reps',str(reps)]
    for name in (['validation_clean_controlled'] if condition=='Clean' else VALIDATIONS):
        args+=['--validation',REMOTE_BASE+'/'+name+'/validation.json']
    if mode:args+=['--mode',mode]
    r=c.python('4',"import subprocess,json;from pathlib import Path;p=Path("+repr(REMOTE_BASE)+");q=subprocess.Popen("+repr(args)+",cwd="+repr(HOME)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(tag+'.log')+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    (BASE/(tag+'_launch.json')).write_text(json.dumps(r));print(json.dumps(r))


def refresh():
    c=control();cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab'}
    for name in ['rospacer/sender_minphy.py','rospacer/__main__.py','tools/w1_sender_local_smoke.py']:
        cam.write('4',HOME+'/'+name,(ROOT/name).read_bytes())
    public=json.loads((BASE/'deployment.json').read_text())['restricted_public_key']
    commands=['iw dev wlp2s0 link','iw dev wlp2s0 info','cat /proc/net/snmp','ss -H -lnt']
    commands += [f'timeout -k 2 {s} iperf3 -s -1 -B 192.168.0.5 -p 55946 -J -i .2' for s in range(25,61)]
    forced='case "$SSH_ORIGINAL_COMMAND" in '+ '|'.join(shlex.quote(s) for s in commands)+') exec sh -c "$SSH_ORIGINAL_COMMAND" ;; *) exit 126 ;; esac'
    authorized='restrict,command="'+forced.replace('\\','\\\\').replace('"','\\"')+'" '+public
    c.python('5',"from pathlib import Path;f=Path.home()/'.ssh/authorized_keys';key="+repr(public.split()[1])+";lines=[s for s in f.read_text().splitlines() if key not in s];lines.append("+repr(authorized)+");f.write_text('\\n'.join(lines)+'\\n');print('{}')")


def install():
    c=control();cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab'}
    for name in ['pyproject.toml','README.md']:
        cam.write('4',HOME+'/'+name,(ROOT/name).read_bytes())
    r=c.python('4',"import subprocess,json;print(json.dumps({'python':subprocess.check_output(['python3','--version'],text=True),'setuptools':subprocess.check_output(['python3','-c','import setuptools;print(setuptools.__version__)'],text=True),'console':subprocess.run(['bash','-c','command -v rospacer'],capture_output=True,text=True).stdout}))")
    (BASE/'install_preflight.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
    wrapper='#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, '+repr(HOME)+')\nfrom rospacer.__main__ import main\ntry:\n    main()\nexcept (ValueError, RuntimeError, OSError) as exc:\n    print("ROSPacer: "+str(exc), file=sys.stderr)\n    sys.exit(2)\n'
    installed=c.python('4',"import json;from pathlib import Path;p=Path.home()/'.local/bin/rospacer';p.parent.mkdir(parents=True,exist_ok=True);s="+repr(wrapper)+";\nif p.exists() and p.read_text()!=s and "+repr('sys.path.insert(0, '+repr(HOME)+')')+" not in p.read_text():raise RuntimeError('preserve existing console')\np.write_text(s);p.chmod(0o755);print(json.dumps({'console':str(p),'local_source':"+repr(HOME)+"}))")
    q=c.extra('4','sudo -n /home/csilab/.local/bin/rospacer sender-govern --help');assert q.returncode==0,q.stderr
    installed['sudo_console_help_verified']=True;(BASE/'installation.json').write_text(json.dumps(installed,indent=2));print(json.dumps(installed))


def lifecycle_checks():
    c=control();cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab'}
    for name in ['rospacer/sender_minphy.py','tools/w1_sender_local_checks.py']:
        cam.write('4',HOME+'/'+name,(ROOT/name).read_bytes())
    args=['sudo','-n','python3','tools/w1_sender_local_checks.py','--base',REMOTE_BASE]
    code="import subprocess,json;from pathlib import Path;p=Path("+repr(REMOTE_BASE)+");q=subprocess.Popen("+repr(args)+",cwd="+repr(HOME)+",stdin=subprocess.DEVNULL,stdout=open(p/'lifecycle_checks.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))"
    r=c.python('4',code);(BASE/'lifecycle_launch.json').write_text(json.dumps(r));print(json.dumps(r))


def application_files():
    c=control();cam=object.__new__(Campaign);cam.c=c;cam.homes={'4':'/home/csilab'}
    cam.write('4',HOME+'/rospacer/sender_minphy.py',(ROOT/'rospacer/sender_minphy.py').read_bytes())
    folder=REMOTE_BASE+'/'+BUNDLE
    code="import json;from pathlib import Path;from rospacer.sender_minphy import bundle_application_files;p=Path("+repr(folder)+");cfg=json.loads((p/'governor.json').read_text());profile=json.loads((p/'profile.json').read_text());bundle_application_files(p,cfg,'fastdds',profile['calibration_socket_bytes']);print('{}')"
    q=c.extra('4','cd '+shlex.quote(HOME)+' && '+shlex.join(['sudo','-n','python3','-c',code]));assert q.returncode==0,q.stderr
    q=c.extra('4','bash -n '+shlex.quote(folder+'/env.bash'));assert q.returncode==0,q.stderr
    print('sender application files generated; no kernel settings changed')


def launch(kind, tag, condition=None):
    c = control()
    args = ['sudo', '-n', 'python3', '-m', 'rospacer', 'sender-'+kind, *common(), '--out', REMOTE_BASE+'/'+tag]
    if kind == 'calibrate': args += ['--rmw', 'fastdds', '--hz', '30']
    else: args += ['--bundle', REMOTE_BASE+'/'+BUNDLE, '--condition', condition]
    code = "import subprocess,json;from pathlib import Path;p=Path("+repr(REMOTE_BASE)+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",cwd="+repr(HOME)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(tag+'.log')+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))"
    r = c.python('4', code); (BASE/(tag+'_launch.json')).write_text(json.dumps(r)); print(json.dumps(r))


def collect():
    c = control()
    code = "import sys,tarfile;from pathlib import Path\np=Path("+repr(REMOTE_BASE)+")\nwith tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:\n for f in p.rglob('*'):\n  if f.is_file():t.add(f,arcname=str(f.relative_to(p)))"
    q = c.extra('4', 'python3 -c '+shlex.quote(code)); assert q.returncode == 0, q.stderr
    dest = BASE/'sender4'; dest.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(q.stdout), mode='r:gz') as t:
        for m in t:
            p = dest/m.name
            if not m.isfile() or '..' in Path(m.name).parts or Path(m.name).is_absolute(): raise ValueError('member')
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(t.extractfile(m).read())


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'prepare': prepare()
    elif mode == 'launch': launch(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv)>4 else None)
    elif mode == 'collect': collect()
    elif mode == 'setup-bench':setup_bench()
    elif mode == 'refresh':refresh()
    elif mode == 'install':install()
    elif mode == 'checks':lifecycle_checks()
    elif mode == 'application-files':application_files()
    elif mode == 'smoke':smoke(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)>5 else None)
