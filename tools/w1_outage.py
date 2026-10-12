"""Finite peer UDP outage on receiver; preserves SSH and removes only own rules."""
import argparse,json,signal,subprocess,time,uuid,ipaddress
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=5);p.add_argument('--delay',type=float,default=8);p.add_argument('--peer',default='192.168.0.3');a=p.parse_args()
    if ipaddress.ip_address(a.peer).version!=4:raise ValueError('IPv4 required')
    if not 0<a.seconds<=10 or not 0<=a.delay<=15:raise ValueError('bounded outage required')
    label='rospacer-w1-'+uuid.uuid4().hex[:12]
    rules=[['INPUT','-i','wlp2s0','-p','udp','-s',a.peer,'-m','comment','--comment',label,'-j','DROP'],['OUTPUT','-o','wlp2s0','-p','udp','-d',a.peer,'-m','comment','--comment',label,'-j','DROP']]
    installed=[];events={'comment':label,'rules':rules,'clock_domain':'receiver monotonic clock','cleanup_errors':[]}
    def interrupt(signum,frame):raise KeyboardInterrupt('outage termination')
    signal.signal(signal.SIGTERM,interrupt)
    def cmd(action,rule):
        q=subprocess.run(['sudo','-n','/usr/sbin/iptables',action,*rule],capture_output=True,text=True,timeout=5)
        if q.returncode:raise RuntimeError(q.stderr)
    try:
        time.sleep(a.delay)
        for rule in rules:cmd('-I',rule);installed.append(rule)
        events['outage_started_monotonic_ns']=time.monotonic_ns();events['outage_started_wall_ns']=time.time_ns()
        Path(a.out).write_text(json.dumps(events,indent=2))
        time.sleep(a.seconds)
    finally:
        for rule in reversed(installed):
            try:cmd('-D',rule)
            except Exception as e:events['cleanup_errors'].append(str(e))
        events['outage_ended_monotonic_ns']=time.monotonic_ns();events['outage_ended_wall_ns']=time.time_ns()
        events['restored']=not events['cleanup_errors'];Path(a.out).write_text(json.dumps(events,indent=2))

if __name__=='__main__':main()
