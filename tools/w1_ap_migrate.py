"""Activate an existing AX1500 profile; roll back unless controller confirms.

No stored connection profiles or passwords are changed. Runs on4/5 only.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def command(argv, timeout=30):
    q = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return {'rc': q.returncode, 'stdout': q.stdout, 'stderr': q.stderr}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['begin', 'switch'])
    p.add_argument('--folder', required=True)
    a = p.parse_args()
    folder = Path(a.folder).resolve()
    if os.geteuid() != 0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:
        raise RuntimeError('root and reviewed run artifact path required')
    if a.mode == 'begin':
        link = command(['iw', 'dev', 'wlp2s0', 'link'])
        if 'SSID: iptime5GAX1500SR2\n' not in link['stdout']:
            raise RuntimeError('only migrate an idle SR2 station')
        q = command(['pgrep', '-af', r'[r]un_sweep|[r]un_campaign|[i]perf3|[t]raffic.py'])
        if q['rc'] != 1:
            raise RuntimeError('preserve active traffic')
        uuid = command(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', 'wlp2s0'])['stdout'].strip()
        profiles = command(['nmcli', '-g', 'connection.uuid', 'connection', 'show', 'iptime5GAX1500'])
        if profiles['rc'] or not uuid:
            raise RuntimeError('saved profile unavailable')
        folder.mkdir(parents=True, exist_ok=False)
        (folder/'original.json').write_text(json.dumps({'uuid': uuid, 'link': link}, indent=2))
        uid, gid = int(os.environ.get('SUDO_UID', 0)), int(os.environ.get('SUDO_GID', 0))
        if folder.name != 'ap_migration':
            raise RuntimeError('dedicated ap_migration folder required')
        os.chown(folder.parent, uid, gid)
        os.chown(folder, uid, gid)
        q = subprocess.Popen(['python3', str(Path(__file__).resolve()), 'switch', '--folder', str(folder)],
                             stdin=subprocess.DEVNULL, stdout=open(folder/'guard.log', 'w'),
                             stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({'pid': q.pid, 'delay_s': 10, 'confirmation_timeout_s': 120}), flush=True)
        return
    original = json.loads((folder/'original.json').read_text())
    result = {}
    confirmed = False
    try:
        time.sleep(10)
        result['activate'] = command(['nmcli', '--wait', '25', 'connection', 'up', 'id', 'iptime5GAX1500', 'ifname', 'wlp2s0'])
        result['link'] = command(['iw', 'dev', 'wlp2s0', 'link'])
        result['address'] = command(['ip', '-j', 'addr', 'show', 'dev', 'wlp2s0'])
        (folder/'connected.json').write_text(json.dumps(result, indent=2))
        if result['activate']['rc'] or 'SSID: iptime5GAX1500\n' not in result['link']['stdout']:
            raise RuntimeError('AP activation failed')
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            if (folder/'confirmed').exists():
                confirmed = True
                break
            time.sleep(1)
    except Exception as e:
        result['error'] = str(e)
    finally:
        result['controller_confirmed'] = confirmed
        if not confirmed:
            result['rollback'] = command(['nmcli', '--wait', '25', 'connection', 'up', 'uuid', original['uuid'], 'ifname', 'wlp2s0'])
        result['final_link'] = command(['iw', 'dev', 'wlp2s0', 'link'])
        (folder/'final.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
