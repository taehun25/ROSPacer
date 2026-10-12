"""Repeat calibration with explicit1MiB sockets; restore kernel limits finally."""
import argparse
import json
import shlex
import subprocess
import sys

from deploy import ROOT, ssh
from w1_b2 import pair_check
from w1_calibrate import remote


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    a = p.parse_args()
    pair_check()
    base = ROOT/'runs'/a.run
    if (base/'calibration_1mib').exists():
        raise RuntimeError('preserve existing calibration')
    before = {}
    for h in ['12', '10']:
        before[h] = remote(h, "import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k],text=True)) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
    errors = []
    try:
        for h in before:
            q = ssh(h, shlex.join(['sudo', '-n', '/sbin/sysctl', '-w', 'net.core.rmem_max=1048576', 'net.core.wmem_max=1048576']))
            if q.returncode:
                raise RuntimeError(q.stderr.decode())
        q = subprocess.run([sys.executable, 'tools/w1_calibrate.py', '--run', a.run,
                            '--label', 'calibration_1mib', '--socket-bytes', '1048576'], cwd=ROOT)
        if q.returncode:
            raise RuntimeError('calibration failed; preserve raw data')
    finally:
        after = {}
        for h, limits in before.items():
            q = ssh(h, shlex.join(['sudo', '-n', '/sbin/sysctl', '-w']+[k+'='+str(v) for k, v in limits.items()]))
            if q.returncode:
                errors.append({'host': h, 'stderr': q.stderr.decode()})
            try:
                after[h] = remote(h, "import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k],text=True)) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
            except Exception as e:
                errors.append({'host': h, 'error': str(e)})
        result = {'before': before, 'after': after, 'errors': errors, 'restored': before == after and not errors}
        (base/'buffer_calibration_restoration.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
        if not result['restored']:
            raise RuntimeError('kernel buffer limits not restored')


if __name__ == '__main__':
    main()
