"""Finite, raw survey polling probe. Does not reinterpret busy or TX."""
import argparse
import json
from pathlib import Path
import re
import socket
import subprocess
import threading
import time


def snapshot(dev):
    r = {'wall_ns': time.time_ns(), 'mono_s': time.monotonic()}
    for key, args in [('survey', ['iw','dev',dev,'survey','dump']),
                      ('station', ['iw','dev',dev,'station','dump'])]:
        p = subprocess.run(args, capture_output=True, text=True, timeout=4)
        r[key] = {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    active = next((s for s in re.split(r'(?=Survey data from)',r['survey']['stdout']) if '[in use]' in s),'')
    r['counters'] = {}
    for name, key in [('active','active_s'),('busy','busy_s'),('transmit','tx_s'),('receive','rx_s')]:
        m = re.search('channel '+name+r' time:\s*(\d+)\s*ms',active)
        if m:r['counters'][key] = int(m[1])/1000
    for name,key in [('tx bytes','bytes'),('tx packets','packets'),('tx retries','retries'),('tx failed','failed'),('rx bytes','rx_bytes'),('rx packets','rx_packets'),('tx duration','station_tx_us'),('rx duration','station_rx_us')]:
        m=re.search(re.escape(name)+r':\s*(\d+)',r['station']['stdout'])
        if m:r['counters'][key]=int(m[1])
    for name,key in [('tx bitrate','tx_bps'),('rx bitrate','rx_bps')]:
        m=re.search(re.escape(name)+r':\s*([\d.]+) MBit/s',r['station']['stdout'])
        if m:r['counters'][key]=float(m[1])*1e6
    r['netdev']={k:int((Path('/sys/class/net')/dev/'statistics'/k).read_text()) for k in ['tx_bytes','rx_bytes','tx_packets','rx_packets','tx_dropped','rx_dropped']}
    r['low_level']={}
    phy=(Path('/sys/class/net')/dev/'phy80211').resolve().name
    stats=Path('/sys/kernel/debug/ieee80211')/phy/'statistics'
    for name in ['dot11FCSErrorCount','dot11ACKFailureCount','dot11RTSFailureCount']:
        path=stats/name
        try:r['low_level'][name]=int(path.read_text().strip())
        except (OSError,ValueError):r['low_level'][name]=None
    reader=Path(__file__).with_name('w1_etstats')
    if reader.exists():
        q=subprocess.run([str(reader),dev],capture_output=True,text=True,timeout=4)
        r['etstats_rc']=q.returncode;r['etstats_stderr']=q.stderr
        if q.returncode==0:r['etstats']=json.loads(q.stdout)['stats']
    lines=Path('/proc/net/snmp').read_text().splitlines()
    for labels,values in zip(lines,lines[1:]):
        if labels.startswith('Udp:') and values.startswith('Udp:'):
            r['udp']=dict(zip(labels.split()[1:],map(int,values.split()[1:])));break
    r['read_finished_mono_s']=time.monotonic()
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True);p.add_argument('--dev',default='wlp2s0')
    p.add_argument('--seconds',type=float,required=True);p.add_argument('--interval',type=float,required=True)
    p.add_argument('--mode',choices=['idle','relay','ap_only','observe'],required=True)
    p.add_argument('--peer');p.add_argument('--bind');p.add_argument('--port',type=int,default=55479)
    p.add_argument('--rate',type=int,default=100000000)
    p.add_argument('--pacing-us',type=int,default=1000)
    p.add_argument('--start-wall-ns',type=int)
    a=p.parse_args()
    if not 0<a.seconds<=40 or not 0<=a.interval<=5:p.error('bounded duration and interval required')
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    if a.start_wall_ns:
        wait=(a.start_wall_ns-time.time_ns())/1e9
        if not -1<=wait<=180:p.error('start deadline must be within180seconds')
        time.sleep(max(0,wait))
    rows=[];errors=[];traffic={};done=threading.Event()
    def aggregation():
        records={}
        for file in Path('/sys/kernel/debug/ieee80211').glob('phy*/mt76/tx_stats'):
            try:records[str(file)]=file.read_text()
            except OSError as e:records[str(file)]={'error':str(e)}
        return records
    aggregation_before=aggregation()
    def sample():
        due=time.monotonic()
        while not done.is_set():
            try:rows.append(snapshot(a.dev))
            except Exception as e:errors.append(str(e))
            due+=a.interval
            done.wait(max(0,due-time.monotonic()))
    rows.append(snapshot(a.dev))
    thread=None
    if a.interval>0:
        thread=threading.Thread(target=sample);thread.start()
    try:
        if a.mode in ('idle','observe'):time.sleep(a.seconds)
        else:
            time.sleep(1)
            traffic={'start_wall_ns':time.time_ns(),'start_mono_s':time.monotonic()}
            if a.mode=='relay':
                args=['iperf3','-c',a.peer,'-B',a.bind,'-p',str(a.port),'-u','-b',str(a.rate),'-l','1400','-w','1048576','-t',str(int(a.seconds)),'--pacing-timer',str(a.pacing_us),'-J']
                q=subprocess.run(args,capture_output=True,text=True,timeout=a.seconds+5)
                traffic.update(args=args,rc=q.returncode,stdout=q.stdout,stderr=q.stderr)
            else:
                s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((a.bind,0));s.settimeout(.1)
                payload=b'W1COUNTER'+bytes(1391);n=0;failed=0;due=time.monotonic();end=due+a.seconds
                period=1400*8/a.rate
                while time.monotonic()<end:
                    for i in range(9):
                        try:s.sendto(payload,(a.peer,a.port));n+=1
                        except OSError:failed+=1
                    due+=9*period;time.sleep(max(0,due-time.monotonic()))
                s.close();traffic.update(sent_datagrams=n,send_failures=failed)
            traffic.update(end_wall_ns=time.time_ns(),end_mono_s=time.monotonic())
            time.sleep(1)
    finally:
        done.set()
        if thread:thread.join(timeout=5)
        rows.append(snapshot(a.dev))
        r={'args':vars(a),'rows':rows,'errors':errors,'traffic':traffic,'aggregation_before':aggregation_before,'aggregation_after':aggregation(),'qualification':'Raw counter observation; no busy inclusion or PHY airtime assumption; no E2E timing claim.'}
        out.write_text(json.dumps(r,indent=2))
        first,last=rows[0]['counters'],rows[-1]['counters']
        d={k:last[k]-first[k] for k in first if k in last and not k.endswith('bps')}
        print(json.dumps({'out':str(out),'samples':len(rows),'delta':d,'errors':errors,'traffic_rc':traffic.get('rc')}),flush=True)


if __name__=='__main__':main()
