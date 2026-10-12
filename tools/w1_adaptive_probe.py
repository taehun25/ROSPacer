"""Bounded W1 diagnostic of adaptive actuation under explicit assumptions.

This is not the production adaptive mode. Self-load residual calibration is
still unqualified. Raw busy is interpreted as excluding self TX for this
diagnostic only, and a measured fixed ceiling bounds every actuation.
"""
import argparse
import csv
import json
from pathlib import Path
import signal
import time
from rospacer.linux import Shaper,observe,deltas
from rospacer.model import adaptive_rate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--seconds',type=float,required=True);p.add_argument('--trace',required=True);a=p.parse_args()
    cfg=json.loads(Path(a.config).read_text())
    if cfg.get('w1_diagnostic_only') is not True or not 0<a.seconds<=50 or cfg.get('receiver_phy_snapshot_Bps',0)<=0:
        p.error('explicit diagnostic configuration and measured receiver PHY required')
    old=observe(cfg['dev'])
    if not old['adaptive_ready']:raise RuntimeError('required counters unavailable')
    ceiling=cfg['cap_packet_Bps'];cap=ceiling;shape=Shaper(cfg);end=time.monotonic()+a.seconds
    def stop(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    fields=['monotonic_s','mode','status','cap_packet_Bps','ceiling_packet_Bps','beta','beta_raw','theta','relay_s','raw_busy_s','tx_s','normalized_busy_s','elapsed_s','qdisc_json','class_json','error']
    try:
        shape.install()
        with open(a.trace,'w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            while time.monotonic()<end:
                tick=time.monotonic();new=observe(cfg['dev']);row=dict(monotonic_s=tick,mode='w1_diagnostic_unqualified',status='hold',cap_packet_Bps=cap,ceiling_packet_Bps=ceiling,error='')
                try:
                    d=deltas(old,new);raw=d['busy_s'];d['busy_s']+=d['tx_s'];d['rx_Bps']=cfg['receiver_phy_snapshot_Bps']
                    estimate=adaptive_rate(cfg,d,True)
                    beta_raw=(raw-estimate['relay_s'])/d['elapsed_s']
                    cap=min(ceiling,max(1000,.7*cap+.3*estimate['cap_packet_Bps']))
                    shape.change(cap)
                    row.update(status='updated',cap_packet_Bps=cap,beta=estimate['beta'],beta_raw=beta_raw,theta=estimate['theta'],relay_s=estimate['relay_s'],raw_busy_s=raw,tx_s=d['tx_s'],normalized_busy_s=d['busy_s'],elapsed_s=d['elapsed_s'])
                except ValueError as e:row['error']=str(e)
                old=new;row['qdisc_json']=shape.stats();row['class_json']=shape.class_stats();writer.writerow(row);f.flush()
                time.sleep(max(0,min(.2-(time.monotonic()-tick),end-time.monotonic())))
    finally:shape.close()


if __name__=='__main__':main()
