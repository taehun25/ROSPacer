"""Install signed survey modules with a bounded reconnect/rollback guard.

Requires operator MOK enrollment first. Stock kernel modules are preserved.
No forced module unloading, Secure Boot changes, or AP changes are performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

MODULES = ['mt76', 'mt76_connac_lib', 'mt792x_lib', 'mt7921_common', 'mt7921e']
ROOT = Path('/var/lib/rospacer-survey')


def command(argv, timeout=35):
    q = subprocess.run(argv,capture_output=True,text=True,timeout=timeout,env=dict(os.environ,LC_ALL='C'))
    return {'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}


def checked(argv, timeout=35):
    q = command(argv,timeout)
    if q['rc']:
        raise RuntimeError(str(argv)+': '+q['stderr'])
    return q['stdout'].strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(folder, name, value):
    path = folder/name
    path.write_text(json.dumps(value,indent=2))
    os.chmod(path,0o644)


def wait_for_interface(timeout=20):
    start = time.monotonic()
    last = {}
    while time.monotonic()-start < timeout:
        last['iw'] = command(['iw','dev','wlp2s0','info'],5)
        last['nm'] = command(['nmcli','-g','GENERAL.DEVICE,GENERAL.STATE','device','show','wlp2s0'],5)
        lines = last['nm']['stdout'].splitlines()
        code = int(lines[1].split()[0]) if len(lines)>1 and lines[1].split()[0].isdigit() else 0
        # NM knows the interface before its supplicant is ready. Allow stable
        # disconnected, connected, or failed states; don't interrupt activation.
        if last['iw']['rc'] == 0 and last['nm']['rc'] == 0 and lines[0] == 'wlp2s0' and code in (30,100,120):
            return {'rc':0,'seconds':time.monotonic()-start,'last':last}
        time.sleep(.5)
    return {'rc':124,'seconds':time.monotonic()-start,'last':last}


def reconnect(uuid):
    q = command(['iw','dev','wlp2s0','link'])
    active = command(['nmcli','-g','GENERAL.CON-UUID','device','show','wlp2s0'])
    if q['rc'] == 0 and 'SSID: iptime5GAX1500\n' in q['stdout'] and active['rc'] == 0 and active['stdout'].strip() == uuid:
        return {'rc':0,'stdout':'NetworkManager automatically restored the original connection.\n','stderr':''}
    return command(['nmcli','--wait','25','connection','up','uuid',uuid,'ifname','wlp2s0'])


def rollback(config):
    result = {'unload':command(['modprobe','-r','mt7921e'])}
    target = Path(config['override'])
    expected = Path('/lib/modules')/config['kernel']/'updates/rospacer-survey'
    if target != expected or not target.resolve().is_relative_to((Path('/lib/modules')/config['kernel']).resolve()):
        raise ValueError('unsafe rollback target')
    for name in config['files']:
        path = target/name
        if path.parent != target or path.suffix != '.ko':
            raise ValueError('unsafe module filename')
        if path.exists():
            path.unlink()
    if target.exists():
        target.rmdir()
    result['depmod'] = command(['depmod','-a',config['kernel']])
    result['load_stock'] = command(['modprobe','mt7921e'])
    result['interface_ready'] = wait_for_interface()
    result['reconnect'] = reconnect(config['uuid'])
    result['link'] = command(['iw','dev','wlp2s0','link'])
    result['stock_path'] = command(['modinfo','-n','mt7921e'])
    return result


def begin(folder):
    kernel = os.uname().release
    signed = json.loads((folder/'sign_result.json').read_text())
    if signed['kernel'] != kernel:
        raise ValueError('rebuild and sign for the running kernel after reboot')
    cert = Path(signed['certificate_path'])
    if cert != ROOT/'MOK.der' or digest(cert) != signed['certificate_sha256']:
        raise ValueError('certificate mismatch')
    q = command(['mokutil','--test-key',str(cert)])
    if q['rc'] not in (0, 1) or not (' is already enrolled' in q['stdout'] or ' is enrolled' in q['stdout']):
        raise ValueError('operator MOK enrollment is required: '+q['stdout'])
    q = command(['pgrep','-af',r'[r]un_campaign|[r]un_sweep|[i]perf3|[t]raffic.py'])
    if q['rc'] != 1:
        raise ValueError('preserve existing experiment processes')
    link = checked(['iw','dev','wlp2s0','link'])
    info = checked(['iw','dev','wlp2s0','info'])
    if 'SSID: iptime5GAX1500\n' not in link+'\n' or 'channel 149 ' not in info:
        raise ValueError('require the previously identified AX1500 channel149 station')
    uuid = checked(['nmcli','-g','GENERAL.CON-UUID','device','show','wlp2s0'])
    if not uuid:
        raise ValueError('saved connection UUID missing')
    stock = {name:{'path':checked(['modinfo','-n',name]),
                   'srcversion':checked(['modinfo','-F','srcversion',name])} for name in MODULES}
    for v in stock.values():
        path = Path(v['path'])
        if not path.is_relative_to(Path('/lib/modules')/kernel/'kernel'):
            raise ValueError('unexpected pre-existing module override')
        v['sha256'] = digest(path)
    target = Path('/lib/modules')/kernel/'updates/rospacer-survey'
    if target.exists():
        raise ValueError('preserve existing override; review before reinstallation')
    source = folder/'source'/('ubuntu_'+kernel.split('-')[1])/'mt76'
    files = {}
    for rel, metadata in signed['modules'].items():
        path = source/rel
        if not path.resolve().is_relative_to(source) or digest(path) != metadata['sha256_signed']:
            raise ValueError('signed module hash mismatch')
        if checked(['modinfo','-F','signer',str(path)]) != metadata['signer']:
            raise ValueError('signer mismatch')
        if not checked(['modinfo','-F','vermagic',str(path)]).startswith(kernel+' '):
            raise ValueError('vermagic mismatch')
        files[path.name] = {'source':str(path),'sha256':metadata['sha256_signed']}
    if set(files) != {'mt76.ko','mt76-connac-lib.ko','mt792x-lib.ko','mt7921-common.ko','mt7921e.ko'}:
        raise ValueError('unexpected module set')
    config = {'kernel':kernel,'folder':str(folder),'override':str(target),'files':files,
              'uuid':uuid,'original_link':link,'original_info':info,'stock':stock,
              'token':secrets.token_hex(16),'delay_s':8,'confirm_timeout_s':180}
    state = ROOT/('runtime-'+kernel)
    if state.exists():
        raise ValueError('preserve previous root guard state')
    state.mkdir(mode=0o700)
    guard = state/'guard.py'
    shutil.copyfile(Path(__file__).resolve(),guard)
    os.chmod(guard,0o700)
    cfg = state/'config.json'
    cfg.write_text(json.dumps(config,indent=2))
    os.chmod(cfg,0o600)
    record(folder,'install_plan.json',config)
    q = subprocess.Popen(['python3',str(guard),'guard','--config',str(cfg)],stdin=subprocess.DEVNULL,
                          stdout=open(state/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'pid':q.pid,'token':config['token'],'delay_s':8,'confirmation_timeout_s':180}),flush=True)


def guard(cfg):
    config = json.loads(cfg.read_text())
    folder, target = Path(config['folder']), Path(config['override'])
    result = {'kernel':config['kernel'],'confirmed':False}
    try:
        time.sleep(config['delay_s'])
        target.mkdir(parents=True,mode=0o755)
        for name, metadata in config['files'].items():
            dest = target/name
            shutil.copyfile(metadata['source'],dest)
            os.chmod(dest,0o644)
            if digest(dest) != metadata['sha256']:
                raise ValueError('module changed during installation')
        checked(['depmod','-a',config['kernel']])
        result['unload'] = command(['modprobe','-r','mt7921e'])
        if result['unload']['rc']:
            raise RuntimeError('normal unload failed; no forced unload attempted')
        result['load'] = command(['modprobe','mt7921e'])
        if result['load']['rc']:
            raise RuntimeError('signed replacement could not be loaded')
        result['interface_ready'] = wait_for_interface()
        if result['interface_ready']['rc']:
            raise RuntimeError('interface did not become ready after driver reload')
        result['reconnect'] = reconnect(config['uuid'])
        if result['reconnect']['rc']:
            raise RuntimeError('reconnect failed')
        result['link'] = command(['iw','dev','wlp2s0','link'])
        result['address'] = command(['ip','-j','addr','show','dev','wlp2s0'])
        result['survey'] = command(['iw','dev','wlp2s0','survey','dump'])
        result['loaded_srcversions'] = {name:Path('/sys/module',name,'srcversion').read_text().strip() for name in MODULES}
        result['expected_srcversions'] = {name:checked(['modinfo','-F','srcversion',name]) for name in MODULES}
        if result['loaded_srcversions'] != result['expected_srcversions']:
            raise RuntimeError('loaded modules do not match the installed replacements')
        record(folder,'connected.json',result)
        deadline = time.monotonic()+config['confirm_timeout_s']
        while time.monotonic() < deadline:
            marker = folder/'confirmed.json'
            if marker.exists() and json.loads(marker.read_text()).get('token') == config['token']:
                result['confirmed'] = True
                break
            time.sleep(1)
    except Exception as e:
        result['error'] = str(e)
    finally:
        if not result['confirmed']:
            result['rollback'] = rollback(config)
        record(folder,'install_final.json',result)
        print(json.dumps(result),flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['begin','guard','rollback'])
    p.add_argument('--folder',type=Path)
    p.add_argument('--config',type=Path)
    a = p.parse_args()
    if os.geteuid() != 0:
        raise ValueError('root required')
    if a.mode == 'begin':
        if not a.folder or a.folder.resolve().parts[-3:] != ('w1_completion_readiness','survey_driver_fix','staged'):
            raise ValueError('dedicated stage required')
        begin(a.folder.resolve())
    else:
        if not a.config or not a.config.resolve().is_relative_to(ROOT):
            raise ValueError('root-owned guard configuration required')
        if a.mode == 'guard':
            guard(a.config.resolve())
        else:
            config = json.loads(a.config.read_text())
            result = rollback(config)
            record(Path(config['folder']),'manual_rollback.json',result)
            print(json.dumps(result),flush=True)
