"""Bounded Linux job wrapper and impairment/clock collectors for W2."""
import argparse,json,subprocess,time,os,signal,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def command(argv,timeout=4):
    try:
        q=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        return {'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
    except subprocess.TimeoutExpired:return {'rc':124,'stdout':'','stderr':'timeout'}

def sampler(task,folder):
    from rospacer.linux import observe
    end=time.monotonic()+task['duration'];last=0
    with (folder/'telemetry.jsonl').open('w') as f,(folder/'clock.jsonl').open('w') as cf:
        while time.monotonic()<end:
            tick=time.monotonic();row={'wall_ns':time.time_ns(),'monotonic_s':tick,'wireless':observe(task['dev']),
               'ss':command(['ss','-uampn']), 'qdisc':command(['tc','-j','-s','qdisc','show','dev',task['dev']]),
               'class':command(['tc','-j','-s','class','show','dev',task['dev']]),'snmp':Path('/proc/net/snmp').read_text()}
            if tick-last>=.8:
                cr={'wall_ns':time.time_ns(),'monotonic_s':tick}
                for k,a in [('tracking',['chronyc','-n','tracking']),('sources',['chronyc','-n','sources']),('ntpdata',['chronyc','-n','ntpdata'])]:
                    q=command(a,1);cr[k]={'exit_code':q['rc'],'stdout':q['stdout'],'stderr':q['stderr']}
                cf.write(json.dumps(cr)+'\n');cf.flush();last=tick
            f.write(json.dumps(row)+'\n');f.flush();time.sleep(max(0,.1-(time.monotonic()-tick)))

def iperf_server(task,folder):
    """One independent single-use server per phase avoids restart races."""
    children=[];deadline=time.monotonic()+task['duration']
    try:
        for port in task['ports']:
            with (folder/('server_'+str(port)+'.json')).open('w') as out,(folder/('server_'+str(port)+'.stderr')).open('w') as err:
                p=subprocess.Popen(['iperf3','-s','-1','-B',task['source'],'-p',str(port),'-J','-i','1'],stdout=out,stderr=err,start_new_session=True)
            children.append((port,p))
        for _ in range(40):
            if any(p.poll() is not None for _,p in children):raise RuntimeError('iperf server exited before ready')
            listeners=command(['ss','-H','-lnt'])['stdout']
            if all(':'+str(port)+' ' in listeners for port,_ in children):break
            time.sleep(.1)
        else:raise RuntimeError('iperf listener readiness timeout')
        (folder/'ready.json').write_text(json.dumps({'ready':True,'ports':task['ports'],'wall_ns':time.time_ns()}))
        while time.monotonic()<deadline:
            if all(p.poll() is not None for _,p in children):break
            time.sleep(.2)
        if any(p.poll() is None for _,p in children):raise RuntimeError('iperf server phase did not complete before deadline')
        if any(p.returncode!=0 for _,p in children):raise RuntimeError('iperf single-use server failed')
    finally:
        for _,p in children:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=2)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def impairment(task,folder):
    start=task['start_wall'];events=[];dev=task['dev'];p=None;children=[]
    while time.time()<start:time.sleep(max(0,min(.1,start-time.time())))
    try:
        if task['condition']=='D3':
            time.sleep(15);before=time.time_ns();r=command(['nmcli','radio','wifi','off']);events.append({'event':'wifi_off','wall_ns':before,'result':r,'monotonic_ns':time.monotonic_ns()})
            time.sleep(5);r=command(['nmcli','radio','wifi','on']);command(['nmcli','connection','up','uuid',task['connection'],'ifname',dev],15)
            command(['iw','dev',dev,'set','power_save','off'])
            events.append({'event':'wifi_restored','wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'result':r})
        else:
            from w2_protocol import competition_schedule
            for phase in competition_schedule(task['condition'],task['seconds'],task['port']):
                offset,duration,factor=phase['offset'],phase['duration'],phase['factor']
                target=start+offset
                while time.time()<target:time.sleep(max(0,min(.1,target-time.time())))
                event={'event':'competition','wall_ns':time.time_ns(),'offset':offset,'requested_factor':factor,'port':phase['port']};events.append(event)
                if factor==0:time.sleep(max(0,target+duration-time.time()));continue
                args=['iperf3','-c',task['peer'],'-B',task['source'],'-p',str(phase['port']),'-u','-b',str(0 if factor is None else round(task['C0']*8*factor)),'-l','1400','-w','1048576','--connect-timeout','3000','-t',str(duration),'-J']
                with (folder/('competition_'+str(offset)+'.json')).open('w') as out,(folder/('competition_'+str(offset)+'.stderr')).open('w') as err:
                    p=subprocess.Popen(args,stdout=out,stderr=err,start_new_session=True)
                children.append((p,event,target+duration+8))
            while time.time()<start+task['seconds']:time.sleep(max(0,min(.1,start+task['seconds']-time.time())))
            for p,event,deadline in children:
                try:p.wait(timeout=max(.1,deadline-time.time()))
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                event['rc']=p.returncode
    finally:
        for p,_,_ in children:
            if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=3)
        if task['condition']=='D3':
            command(['nmcli','radio','wifi','on'])
            connected=command(['nmcli','-g','GENERAL.STATE','device','show',dev])
            if not connected['stdout'].strip().startswith('100'):command(['nmcli','connection','up','uuid',task['connection'],'ifname',dev],15)
            command(['iw','dev',dev,'set','power_save','off'])
        (folder/'impairment.json').write_text(json.dumps(events,indent=2))

def main():
    def stop(*_):raise KeyboardInterrupt('termination requested')
    signal.signal(signal.SIGTERM,stop)
    a=argparse.ArgumentParser();a.add_argument('--task',required=True);x=a.parse_args();t=json.loads(Path(x.task).read_text());folder=Path(t['folder']);folder.mkdir(parents=True,exist_ok=True)
    r={'started_wall':time.time(),'kind':t['kind']};p=None
    try:
        if t['kind']=='sampler':sampler(t,folder)
        elif t['kind']=='impairment':impairment(t,folder)
        elif t['kind']=='iperf_server':iperf_server(t,folder)
        else:
            p=subprocess.Popen(t['argv'],cwd=t['cwd'],stdout=open(folder/(t.get('log','job')+'.log'),'w'),stderr=subprocess.STDOUT,start_new_session=True)
            (folder/'process.json').write_text(json.dumps({'pid':p.pid,'start_token':Path('/proc',str(p.pid),'stat').read_text().split()[21]}))
            try:r['rc']=p.wait(timeout=t['timeout'])
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);time.sleep(2);os.killpg(p.pid,signal.SIGKILL) if p.poll() is None else None;r['rc']=p.wait();r['timeout']=True
    except BaseException as e:r['error']=str(e);r['rc']=1
    finally:
        if p and p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        r.setdefault('rc',0);r['ended_wall']=time.time();(folder/'done.json').write_text(json.dumps(r,indent=2))

if __name__=='__main__':main()
