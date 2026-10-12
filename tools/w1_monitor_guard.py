"""Finite passive monitor companion; preserve the existing managed interface."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
import os


def run(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=6)
    if q.returncode:raise RuntimeError(q.stderr)
    return q.stdout


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=40);p.add_argument('--start-marker');a=p.parse_args()
    if not 1<a.seconds<=45:p.error('bounded duration required')
    if os.geteuid()!=0:p.error('root required for explicitly creating the companion monitor')
    if Path('/sys/class/net/w1mon').exists():raise RuntimeError('preserve pre-existing monitor')
    out=Path(a.out).resolve();created=False;child=None;result={}
    if 'ROSPacer' not in out.parts or 'runs' not in out.parts or out.exists():raise ValueError('fresh experiment capture path required')
    marker=Path(a.start_marker).resolve() if a.start_marker else None
    if marker and marker.parent!=out.parent:raise ValueError('marker must be in the same experiment folder')
    if marker and marker.exists():raise ValueError('fresh start marker required; preserve the earlier attempt')
    def stop(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        result['managed_before']=run(['iw','dev','wlp2s0','info'])
        run(['iw','dev','wlp2s0','interface','add','w1mon','type','monitor','flags','control','otherbss']);created=True
        run(['ip','link','set','dev','w1mon','up'])
        result['monitor']=run(['iw','dev','w1mon','info'])
        if marker:
            result['waiting_for_start']=True
            out.with_suffix('.state.json').write_text(json.dumps(result,indent=2))
            print(json.dumps({'ready':True,'waiting_for_controller_s':120}),flush=True)
            end=time.monotonic()+120
            while not marker.exists() and time.monotonic()<end:time.sleep(.5)
            if not marker.exists():raise RuntimeError('controller start timeout; remove companion monitor')
            result['waiting_for_start']=False
        result['capture_start_wall_ns']=time.time_ns()
        expression='wlan addr1 3c:0a:f3:02:d9:3b or wlan addr2 3c:0a:f3:02:d9:3b or wlan addr1 3c:0a:f3:02:e4:c7 or wlan addr2 3c:0a:f3:02:e4:c7'
        child=subprocess.Popen(['tcpdump','-i','w1mon','-s','160','-w',str(out),expression],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=open(str(out)+'.capture.log','w'))
        (out.with_suffix('.state.json')).write_text(json.dumps(result,indent=2))
        time.sleep(a.seconds)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        result['error']=str(e)
    finally:
        if child:
            child.send_signal(signal.SIGINT)
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if created:
            try:run(['iw','dev','w1mon','del'])
            except Exception as e:result['cleanup_error']=str(e)
        result['monitor_removed']=not Path('/sys/class/net/w1mon').exists()
        result['capture_end_wall_ns']=time.time_ns()
        result['managed_after']=run(['iw','dev','wlp2s0','info'])
        (out.with_suffix('.state.json')).write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
