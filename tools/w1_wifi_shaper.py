"""Owned high-cap HTB/fq diagnostic; only the probe UDP port is additionally classified."""
import argparse,json,signal,time,ipaddress,re
from pathlib import Path
from rospacer.linux import Shaper

def main():
    p=argparse.ArgumentParser();p.add_argument('--burst',type=int,required=True);p.add_argument('--out',required=True);p.add_argument('--dev',default='wlo1');p.add_argument('--peer',default='192.168.0.4');p.add_argument('--port',type=int,default=55311);a=p.parse_args()
    if a.burst not in [1500,65536]:raise ValueError('reviewed burst values only')
    if ipaddress.ip_address(a.peer).version!=4 or not 1024<=a.port<=65535 or not re.fullmatch('[A-Za-z0-9_.:-]+',a.dev):raise ValueError('invalid probe endpoint')
    cfg={'dev':a.dev,'mtu':1500,'unit_bytes':1472,'peers':[a.peer],'cap_packet_Bps':25000000,'burst_bytes':a.burst,'fq_flow_limit':1000,'fq_limit':4096}
    shaper=Shaper(cfg)
    def stop(signum,frame):raise KeyboardInterrupt('finite diagnostic termination')
    signal.signal(signal.SIGTERM,stop)
    try:
        shaper.install()
        shaper.tc('filter','add','dev',a.dev,'parent','7ac0:','protocol','ip','prio','50','u32','match','ip','protocol','17','0xff','match','ip','dst',a.peer+'/32','match','ip','dport',str(a.port),'0xffff','flowid','7ac0:10')
        end=time.monotonic()+17
        with open(a.out,'w') as f:
            while time.monotonic()<end:
                f.write(json.dumps({'mono':time.monotonic(),'qdisc':shaper.stats(),'class':shaper.class_stats()})+'\n');f.flush();time.sleep(.2)
    finally:shaper.close()

if __name__=='__main__':main()
