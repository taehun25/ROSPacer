"""Finite experimental ACK pacing; ordinary receiver DDS, no stats feedback.

This is an explicitly selected experiment, not an approved production governor.
The original wireless sender model and receiver-assisted route are unchanged.
"""
import argparse,json,math,os,signal,subprocess,sys,time
from pathlib import Path
from .sender_protocol import observe
from .linux import Shaper

def validate(cfg,source,peer,seconds):
    if cfg.get('experimental_ack_trial') is not True:raise ValueError('explicit experimental ACK configuration required')
    if not math.isfinite(seconds) or not 0<seconds<=100:raise ValueError('finite ACK experiment required')
    if cfg.get('payload_bytes')!=1048576 or cfg.get('peers')!=[peer] or source==peer:raise ValueError('one 1MiB IPv4 source/reader trial required')
    if cfg.get('dev')!='wlp2s0':raise ValueError('laboratory Wi-Fi scope required')
    cap=cfg.get('ack_ceiling_packet_Bps')
    if not isinstance(cap,(int,float)) or not math.isfinite(cap) or cap<=0:raise ValueError('finite positive ceiling required')
    if cfg.get('cap_packet_Bps')!=cap:raise ValueError('ACK and installed packet cap must agree')
    if 'receiver_feedback' in cfg:raise ValueError('receiver stats feedback prohibited')
    return cap

class Actuator:
    def __init__(self,shaper,mode,ceiling):self.shaper,self.mode,self.ceiling=shaper,mode,ceiling;self.applied=ceiling;self.changes=0
    def __call__(self,cap,status,reason):
        if not math.isfinite(cap) or not .1*self.ceiling<=cap<=self.ceiling:raise ValueError('recommendation escaped frozen bounds')
        target=self.ceiling if self.mode=='fixed' else cap
        if status=='hold' and self.mode=='ack':target=self.applied
        if abs(target-self.applied)>.5:
            self.shaper.change(target);self.applied=target;self.changes+=1
        return {'applied_packet_Bps':self.applied,'htb_changes':self.changes,'class_json':self.shaper.class_stats(),'qdisc_json':self.shaper.stats()}

def guard(folder,dev,seconds,pid,start_token):
    deadline=time.monotonic()+seconds;end=folder/'shaper.end'
    while time.monotonic()<deadline and not end.exists():time.sleep(.5)
    if end.exists():return
    stat=Path('/proc')/str(pid)/'stat'
    if stat.exists() and stat.read_text().split()[21]==start_token:
        os.kill(pid,signal.SIGTERM);time.sleep(2)
    roots=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev',dev]))
    if any(x.get('root') and x.get('handle')==Shaper.HANDLE for x in roots):
        subprocess.run(['tc','qdisc','del','dev',dev,'root','handle',Shaper.HANDLE],check=True)
    (folder/'guard_expired.json').write_text(json.dumps({'expired':True,'pid':pid,'qdisc_after':json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev',dev]))}))

def main():
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--source');p.add_argument('--peer');p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=65);p.add_argument('--mode',choices=['ack','fixed'],default='ack');p.add_argument('--mask-start',type=float);p.add_argument('--mask-seconds',type=float,default=0);p.add_argument('--guard-pid',type=int);p.add_argument('--guard-start-token');p.add_argument('--guard-dev');a=p.parse_args();folder=Path(a.out)
    if a.guard_pid is not None:guard(folder,a.guard_dev,a.seconds,a.guard_pid,a.guard_start_token);return
    cfg=json.loads(Path(a.config).read_text());ceiling=validate(cfg,a.source,a.peer,a.seconds)
    if os.geteuid()!=0:raise RuntimeError('root required for this finite HTB experiment')
    if folder.exists():raise ValueError('preserve existing trial output')
    folder.mkdir(parents=True);shaper=Shaper(cfg);result={};error=None;actuator=Actuator(shaper,a.mode,ceiling);old=signal.getsignal(signal.SIGTERM)
    def stop(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        shaper.install()
        start=Path('/proc/self/stat').read_text().split()[21]
        helper=subprocess.Popen([sys.executable,'-m','rospacer.sender_ack_live','--out',str(folder),'--seconds',str(a.seconds+5),'--guard-pid',str(os.getpid()),'--guard-start-token',start,'--guard-dev',cfg['dev']],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
        (folder/'guard.json').write_text(json.dumps({'pid':helper.pid,'expires_s':a.seconds+5}))
        result=observe(cfg['dev'],a.source,a.peer,cfg['payload_bytes'],a.seconds,str(folder/'protocol'),ceiling,a.mask_start,a.mask_seconds,actuator)
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        shaper.close();(folder/'shaper.end').write_text('end');signal.signal(signal.SIGTERM,old)
        roots=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev',cfg['dev']]))
        result.update(HTB_applied=True,mode=a.mode,HTB_changes=actuator.changes,error=error,restored=all(x['kind']=='noqueue' for x in roots),qdisc_after=roots)
        (folder/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result.get(k) for k in ['mode','observed_samples','confirmed_samples','HTB_changes','error','restored']}),flush=True)
    if error:raise RuntimeError(error)
if __name__=='__main__':main()
