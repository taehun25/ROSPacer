"""Renew an owned expiry guard without changing experiment settings/baseline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=['power','wire'],required=True);p.add_argument('--folder',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args()
    folder=Path(a.folder).resolve();base=Path(__file__).resolve().parents[1]
    if os.geteuid()!=0 or not folder.is_relative_to(base/'runs'):raise ValueError('root and owned run path required')
    if (folder/('end_session' if a.kind=='power' else 'end')).exists() or (folder/'restoration.json').exists():raise ValueError('guard already ended')
    tool=base/'tools'/('w1_session.py' if a.kind=='power' else 'w1_management_guard.py')
    cmd=(Path('/proc')/str(a.pid)/'cmdline').read_bytes().split(b'\0')
    if bytes(str(tool),'utf8') not in cmd or b'guard' not in cmd or bytes(str(folder),'utf8') not in cmd:raise ValueError('preserve unrelated process')
    baseline=folder/'baseline.json';digest=hashlib.sha256(baseline.read_bytes()).hexdigest();cfg=json.loads(baseline.read_text())
    args=['python3',str(tool),'guard','--folder',str(folder)]+(['--dev',cfg['dev']] if a.kind=='power' else ['--address',cfg['address']])
    new=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=open(folder/'guard_renewed.log','a'),stderr=subprocess.STDOUT,start_new_session=True)
    try:os.kill(a.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==digest
    result={'old_pid':a.pid,'new_pid':new.pid,'expiry_s':3600,'baseline_sha256':digest,'settings_changed':False,'wall_ns':time.time_ns()}
    (folder/'renewal.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
