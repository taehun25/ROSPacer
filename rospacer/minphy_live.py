"""Explicit finite budget experiment; offline peer PHY, no receiver daemon.

Budget validation is separate from original occupancy decomposition approval.
"""
import argparse,csv,hashlib,json,os,signal,subprocess,time,re
from pathlib import Path
from collections import deque
from .linux import Shaper,observe
from .sender_radio import window_uplink
from .minphy_radio import estimate

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--profile',required=True);p.add_argument('--qualification',required=True);p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=65);a=p.parse_args();cfg=json.loads(Path(a.config).read_text());profile=json.loads(Path(a.profile).read_text());qualification=json.loads(Path(a.qualification).read_text());folder=Path(a.out)
    if not cfg.get('experimental_minphy_trial') or not 0<a.seconds<=90 or cfg['peers']!=['192.168.0.5'] or cfg['dev']!='wlp2s0':raise ValueError('explicit finite laboratory budget experiment required')
    if 'receiver_feedback' in cfg or qualification.get('capacity_budget_gate_pass') is not True:raise ValueError('budget gate failed or receiver daemon dependency')
    if qualification['profile_sha256']!=hashlib.sha256(Path(a.profile).read_bytes()).hexdigest():raise ValueError('budget profile changed')
    if profile['source_sha256']!=hashlib.sha256(Path(__file__).with_name('minphy_radio.py').read_bytes()).hexdigest():raise ValueError('budget model changed')
    for name,digest in profile['kernel_modules'].items():
        if (Path('/sys/module')/name/'srcversion').read_text().strip()!=digest:raise ValueError('driver scope changed')
    if folder.exists():raise ValueError('preserve existing output')
    folder.mkdir(parents=True);cfg={**cfg,'cap_packet_Bps':min(cfg['cap_packet_Bps'],profile['ceiling_packet_Bps'])};cap=cfg['cap_packet_Bps'];shaper=Shaper(cfg);samples=deque();changes=0;errors={};error=None;updates=0;boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();old=signal.getsignal(signal.SIGTERM)
    def stop(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        first=observe(cfg['dev'])
        if 'Station '+profile['AP']+' ' not in first['station_raw']:raise ValueError('AP scope changed')
        info=subprocess.check_output(['iw','dev',cfg['dev'],'info'],text=True)
        if 'channel 149 ' not in info or 'width: 80 MHz' not in info:raise ValueError('channel scope changed')
        shaper.install();token=Path('/proc/self/stat').read_text().split()[21]
        helper=subprocess.Popen(['python3','-m','rospacer.sender_ack_live','--out',str(folder),'--seconds',str(a.seconds+5),'--guard-pid',str(os.getpid()),'--guard-start-token',token,'--guard-dev',cfg['dev']],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
        (folder/'guard.json').write_text(json.dumps({'pid':helper.pid}));end=time.monotonic()+a.seconds
        with (folder/'trace.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['monotonic_s','status','cap_packet_Bps','occupancy_residual','theta','relay_s','class_json','qdisc_json','error']);writer.writeheader()
            while time.monotonic()<end:
                tick=time.monotonic();row={'monotonic_s':tick,'status':'hold','cap_packet_Bps':cap,'error':''}
                try:
                    sample=observe(cfg['dev']);ap=re.search(r'^Station ([0-9a-f:]{17})',sample['station_raw'],re.M)
                    if not ap:raise ValueError('source AP unavailable')
                    sample.update(boot_id=boot,AP=ap[1]);samples.append(sample)
                    while len(samples)>2 and samples[1]['monotonic_s']<sample['monotonic_s']-3:samples.popleft()
                    if sample['monotonic_s']-samples[0]['monotonic_s']<2:raise ValueError('source observation warming up')
                    current={**sample,'window_tx_Bps':window_uplink(list(samples),14)};e=estimate(profile,samples[0],current);newcap=min(cfg['cap_packet_Bps'],max(1000,.7*cap+.3*e['cap_packet_Bps']))
                    if abs(newcap-cap)>.5:shaper.change(newcap);changes+=1
                    cap=newcap;updates+=1;row.update(status='updated',cap_packet_Bps=cap,occupancy_residual=e['beta'],theta=e['theta'],relay_s=e['relay_s'])
                except (ValueError,KeyError) as e:row['error']=str(e);errors[str(e)]=errors.get(str(e),0)+1
                row.update(class_json=shaper.class_stats(),qdisc_json=shaper.stats());writer.writerow(row);f.flush();time.sleep(max(0,.2-(time.monotonic()-tick)))
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        shaper.close();(folder/'shaper.end').write_text('end');signal.signal(signal.SIGTERM,old);roots=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev',cfg['dev']]))
        result={'updates':updates,'HTB_changes':changes,'hold_reasons':errors,'error':error,'restored':all(q['kind']=='noqueue' for q in roots),'receiver_online_feedback':False,'original_beta_decomposition_approved':False,'production_approved':False};(folder/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    if error:raise RuntimeError(error)
if __name__=='__main__':main()
