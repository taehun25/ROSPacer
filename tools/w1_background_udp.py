"""Finite B2 background without a new TCP handshake for every ON period."""
import argparse
import json
from pathlib import Path
import socket
import struct
import subprocess
import time


def counters():
    lines=Path('/proc/net/snmp').read_text().splitlines()
    for labels,values in zip(lines,lines[1:]):
        if labels.startswith('Udp:') and values.startswith('Udp:'):return dict(zip(labels.split()[1:],map(int,values.split()[1:])))
    return {}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('role',choices=['source','sink']);p.add_argument('--bind',required=True);p.add_argument('--peer');p.add_argument('--port',type=int,default=55483);p.add_argument('--seconds',type=float,required=True);p.add_argument('--delay',type=float,default=0);p.add_argument('--out',required=True)
    p.add_argument('--start-wall-ns',type=int);p.add_argument('--rate',type=int,default=0);p.add_argument('--on-seconds',type=float,default=2);p.add_argument('--off-seconds',type=float,default=2)
    a=p.parse_args()
    if not 0<a.seconds<=200 or not 0<=a.delay<=20 or not 0<a.on_seconds<=40 or not 0<=a.off_seconds<=4:p.error('bounded durations required')
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);old={k:int(subprocess.check_output(['sysctl','-n','net.core.'+k])) for k in ['rmem_max','wmem_max']}
    result={'args':vars(a),'baseline_sysctl':old,'udp_before':counters(),'events':[]};sock=None
    try:
        subprocess.run(['sudo','-n','/sbin/sysctl','-w','net.core.rmem_max=1048576','net.core.wmem_max=1048576'],check=True,capture_output=True,timeout=5)
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1048576);sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1048576);sock.bind((a.bind,a.port if a.role=='sink' else 0));sock.settimeout(.1)
        result['socket_buffers']={'send':sock.getsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF),'receive':sock.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)}
        (out/'ready.json').write_text(json.dumps({'ready':True,'wall_ns':time.time_ns(),'args':vars(a)}));time.sleep(a.delay)
        if a.start_wall_ns:
            wait=(a.start_wall_ns-time.time_ns())/1e9
            if not -1<=wait<=180:raise ValueError('start deadline outside180seconds')
            time.sleep(max(0,wait))
        start=time.monotonic();deadline=start+a.seconds;result['start_mono_s']=start;result['start_wall_ns']=time.time_ns()
        if a.role=='source':
            phase=0;seq=0;tail=bytes(1384)
            while time.monotonic()+2<deadline and not (out/'stop').exists():
                due=start+phase*(a.on_seconds+a.off_seconds)
                if due>time.monotonic():time.sleep(due-time.monotonic())
                row={'phase':phase,'start_mono_s':time.monotonic(),'start_wall_ns':time.time_ns(),'first_seq':seq};sent=0;errors=0;on_start=time.monotonic();on_end=min(deadline,on_start+a.on_seconds);batch=0
                while time.monotonic()<on_end:
                    try:sock.sendto(struct.pack('!4sIQ',b'W1BG',phase,seq)+tail,(a.peer,a.port));sent+=1;seq+=1
                    except OSError:errors+=1
                    batch+=1
                    if a.rate and batch%9==0:
                        sleep=on_start+batch*1400*8/a.rate-time.monotonic()
                        if sleep>0:time.sleep(sleep)
                row.update(sent_datagrams=sent,send_errors=errors,end_mono_s=time.monotonic(),end_wall_ns=time.time_ns());result['events'].append(row)
                (out/'progress.json').write_text(json.dumps(result['events']));phase+=1
        else:
            phases={};bins={};invalid=0
            check_due=start;stopped=False
            while time.monotonic()<deadline and not stopped:
                if time.monotonic()>=check_due:
                    stopped=(out/'stop').exists();check_due=time.monotonic()+.2
                try:data,peer=sock.recvfrom(2048)
                except socket.timeout:continue
                now=time.monotonic()
                if len(data)!=1400 or data[:4]!=b'W1BG' or peer[0]!=a.peer:invalid+=1;continue
                phase,seq=struct.unpack('!IQ',data[4:16]);row=phases.setdefault(phase,{'phase':phase,'first_mono_s':now,'first_wall_ns':time.time_ns(),'packets':0,'bytes':0,'min_seq':seq,'max_seq':seq})
                row.update(last_mono_s=now,last_wall_ns=time.time_ns(),packets=row['packets']+1,bytes=row['bytes']+len(data),min_seq=min(seq,row['min_seq']),max_seq=max(seq,row['max_seq']))
                tick=int((now-start)/.2);bins[tick]=bins.get(tick,0)+len(data)
            result.update(events=list(phases.values()),bins_200ms_bytes=bins,invalid_datagrams=invalid)
        result.update(end_mono_s=time.monotonic(),end_wall_ns=time.time_ns(),udp_after=counters())
    finally:
        if sock:sock.close()
        q=subprocess.run(['sudo','-n','/sbin/sysctl','-w',*['net.core.'+k+'='+str(v) for k,v in old.items()]],capture_output=True,text=True,timeout=5)
        after={k:int(subprocess.check_output(['sysctl','-n','net.core.'+k])) for k in old}
        result['restoration']={'rc':q.returncode,'stderr':q.stderr,'sysctl_after':after,'restored':q.returncode==0 and after==old}
        (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({'role':a.role,'events':len(result['events']),'restored':result['restoration']['restored']}),flush=True)


if __name__=='__main__':main()
