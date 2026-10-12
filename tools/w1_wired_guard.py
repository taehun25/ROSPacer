"""Bounded wired management isolation: allow SSH, NTP, ICMP; reject DDS.

Dedicated chains are removed in finally on timeout or termination. Used only
on the directly connected 192.168.50.0/24 management pair.
"""
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def run(a,check=True):
    return subprocess.run(['iptables','-w','3',*a],check=check,capture_output=True,text=True,timeout=6)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    if os.geteuid()!=0 or not 0<a.seconds<=90:
        p.error('root and bounded duration required')
    chains={'OUTPUT':'RPW1OUT','INPUT':'RPW1IN'}
    added=[];created=[]
    def stop(*args):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        for hook,name in chains.items():
            if run(['-S',name],False).returncode==0:
                raise RuntimeError('preserve pre-existing experiment chain')
            run(['-N',name]);created.append(name)
            run(['-A',name,'-p','icmp','-j','RETURN'])
            for proto,port in [('udp','123'),('tcp','22')]:
                for option in ['--sport','--dport']:
                    run(['-A',name,'-p',proto,option,port,'-j','RETURN'])
            run(['-A',name,'-j','REJECT'])
            rule=['-o' if hook=='OUTPUT' else '-i','enp1s0','-j',name]
            run(['-I',hook,'1',*rule]);added.append((hook,rule))
        Path(a.out).write_text(json.dumps({'installed':True,'seconds':a.seconds,'chains':chains}))
        time.sleep(a.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        stats={name:run(['-L',name,'-v','-n','-x'],False).stdout for name in created}
        errors=[]
        for hook,rule in reversed(added):
            q=run(['-D',hook,*rule],False)
            if q.returncode:errors.append(q.stderr)
        for name in reversed(created):
            run(['-F',name],False)
            q=run(['-X',name],False)
            if q.returncode:errors.append(q.stderr)
        Path(a.out).with_suffix('.restoration.json').write_text(json.dumps({'errors':errors,'stats':stats,'restored':not errors},indent=2))


if __name__=='__main__':
    main()
