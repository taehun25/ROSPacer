"""Build a staged MT7921 survey fix; never replace or reload installed modules."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def run(argv, timeout=240):
    q = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    print(q.stdout, end='', flush=True)
    print(q.stderr, end='', flush=True)
    if q.returncode:
        raise RuntimeError(f'command failed ({q.returncode}): {argv[0]}')
    return q.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--version', choices=['136', '138'], required=True)
    a = p.parse_args()
    folder = a.folder.resolve()
    if not folder.is_relative_to(Path.home()/'ros2_ws/src/large_data_1009/ROSPacer/runs'):
        raise ValueError('dedicated run path required')
    kernel = os.uname().release
    if kernel != '6.8.0-'+a.version+'-generic':
        raise ValueError('running kernel must match the staged Ubuntu source')
    source = folder/'source'/('ubuntu_'+a.version)/'mt76'
    manifest = json.loads((source.parent/'source_manifest.json').read_text())
    for rel, digest in manifest.items():
        path = source/rel
        if not path.resolve().is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('source manifest mismatch: '+rel)
    packages = sorted((folder/'compiler').glob('*.deb'))
    if len(packages) != 5:
        raise ValueError('exact five compiler packages required')
    for path in packages:
        name = run(['dpkg-deb','-f',str(path),'Package'], 10).strip()
        meta = run(['apt-cache','show',name+'=12.3.0-1ubuntu1~22.04.3'], 15)
        expected = re.search(r'^SHA256: (\w+)$', meta, re.M)
        if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected[1]:
            raise ValueError('APT SHA256 mismatch: '+name)
    # Every dependency was resolved in the recorded APT plan; install exactly
    # the five verified local packages without a network fetch or upgrade.
    q = subprocess.run(['dpkg-query','-W','-f=${Version}\n','cpp-12','gcc-12','libasan8','libgcc-12-dev','libtsan2'],capture_output=True,text=True)
    if q.returncode or q.stdout.splitlines() != ['12.3.0-1ubuntu1~22.04.3']*5:
        run(['sudo','-n','dpkg','--install']+[str(p) for p in packages], 180)
    start = time.monotonic()
    run(['make','-C','/lib/modules/'+kernel+'/build','M='+str(source),'CC=gcc-12','-j4','modules'], 240)
    wanted = ['mt76.ko','mt76-connac-lib.ko','mt792x-lib.ko','mt7921/mt7921-common.ko','mt7921/mt7921e.ko']
    result = {'kernel': kernel, 'source_manifest': hashlib.sha256((source.parent/'source_manifest.json').read_bytes()).hexdigest(),
              'build_seconds': time.monotonic()-start, 'modules': {}, 'installed': False, 'loaded': False}
    for rel in wanted:
        path = source/rel
        vermagic = run(['modinfo','-F','vermagic',str(path)], 10).strip()
        if not vermagic.startswith(kernel+' '):
            raise ValueError('module vermagic mismatch')
        result['modules'][rel] = {'sha256_unsigned':hashlib.sha256(path.read_bytes()).hexdigest(), 'vermagic':vermagic}
    (folder/'build_result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'build_complete': True, 'kernel':kernel, 'modules':len(wanted)}), flush=True)


if __name__ == '__main__':
    main()
