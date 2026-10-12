"""Owned high-cap HTB/fq diagnostic; only the probe UDP port is additionally classified."""
import argparse,json,signal,time
from pathlib import Path
from rospacer.linux import Shaper

def main():
    p=argparse.ArgumentParser();p.add_argument('--burst',type=int,required=True);p.add_argument('--out',required=True);a=p.parse_args()
    if a.burst not in [1500,65536]:raise ValueError('reviewed burst values only')
    cfg={'dev':'wlo1','mtu':1500,'unit_bytes':1472,'peers':['192.168.0.4'],'cap_packet_Bps':25000000,'burst_bytes':a.burst,'fq_flow_limit':1000,'fq_limit':4096}
    shaper=Shaper(cfg)
    def stop(signum,frame):raise KeyboardInterrupt('finite diagnostic termination')
    signal.signal(signal.SIGTERM,stop)
    try:
        shaper.install()
        shaper.tc('filter','add','dev','wlo1','parent','7ac0:','protocol','ip','prio','50','u32','match','ip','protocol','17','0xff','match','ip','dst','192.168.0.4/32','match','ip','dport','55311','0xffff','flowid','7ac0:10')
        end=time.monotonic()+27
        with open(a.out,'w') as f:
            while time.monotonic()<end:
                f.write(json.dumps({'mono':time.monotonic(),'qdisc':shaper.stats(),'class':shaper.class_stats()})+'\n');f.flush();time.sleep(.2)
    finally:shaper.close()

if __name__=='__main__':main()
