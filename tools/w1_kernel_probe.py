"""Isolated veth scheduler diagnostic on host12; does not prove Wi-Fi 200Mbps."""
import json,os,subprocess,time,uuid
from pathlib import Path

def cmd(argv):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=15)
 if p.returncode:raise RuntimeError(p.stderr or p.stdout)
 return p.stdout

def main():
 if os.geteuid()!=0:raise RuntimeError('root required')
 user=os.environ.get('SUDO_USER');home=Path('/home')/user
 folder=home/'ros2_ws/src/large_data_1009/ROSPacer/runs/w1_20261012_163000/kernel_probe';folder.mkdir(parents=True,exist_ok=True)
 token=uuid.uuid4().hex[:6];ns='rpw1'+token;tx='w1tx'+token;rx='w1rx'+token
 trials=[];cleanup=[]
 try:
  cmd(['ip','netns','add',ns]);cmd(['ip','link','add',tx,'type','veth','peer','name',rx]);cmd(['ip','link','set',rx,'netns',ns])
  cmd(['ip','addr','add','198.18.0.1/30','dev',tx]);cmd(['ip','link','set',tx,'up'])
  for args in [['ip','link','set','lo','up'],['ip','addr','add','198.18.0.2/30','dev',rx],['ip','link','set',rx,'up']]:cmd(['ip','netns','exec',ns]+args)
  for name,burst in [('baseline',None),('burst1500',1500),('burst65536',65536)]:
   if burst:
    cmd(['tc','qdisc','add','dev',tx,'root','handle','7ac0:','htb','default','10'])
    cmd(['tc','class','add','dev',tx,'parent','7ac0:','classid','7ac0:10','htb','rate','200mbit','ceil','200mbit','burst',str(burst),'cburst',str(burst),'quantum','1500'])
    cmd(['tc','qdisc','add','dev',tx,'parent','7ac0:10','handle','7ac1:','fq','limit','4096','flow_limit','1000','nopacing'])
   log=open(folder/(name+'_server.json'),'w');server=subprocess.Popen(['ip','netns','exec',ns,'timeout','-k','2','16','iperf3','-s','-1','-B','198.18.0.2','-p','55291','-J'],stdout=log,stderr=subprocess.STDOUT)
   time.sleep(.3)
   client=subprocess.Popen(['iperf3','-c','198.18.0.2','-B','198.18.0.1','-p','55291','-u','-b','300M','-l','1400','-t','10','-J'],stdout=open(folder/(name+'_client.json'),'w'),stderr=subprocess.STDOUT)
   trace=[]
   while client.poll() is None:
    trace.append({'mono':time.monotonic(),'qdisc':cmd(['tc','-j','-s','qdisc','show','dev',tx]),'class':cmd(['tc','-s','class','show','dev',tx])});time.sleep(.2)
   server.wait(timeout=7);log.close()
   (folder/(name+'_trace.json')).write_text(json.dumps(trace,indent=2))
   srv=json.loads((folder/(name+'_server.json')).read_text());streams=[r for it in srv.get('intervals',[]) for r in it.get('streams',[])];b=sum(r.get('bytes',0) for r in streams);s=sum(r.get('seconds',0) for r in streams)
   trials.append({'name':name,'burst':burst,'receiver_udp_payload_Mbps':8*b/s/1e6 if s else None,'client_rc':client.returncode})
   if burst:cmd(['tc','qdisc','del','dev',tx,'root'])
 finally:
  for args in [['ip','link','del',tx],['ip','netns','del',ns]]:
   try:cmd(args)
   except Exception as e:cleanup.append(str(e))
  result={'kernel':os.uname().release,'trials':trials,'cleanup_errors':cleanup,'scope':'Isolated veth kernel scheduler diagnostic; Wi-Fi interface and its qdisc untouched; does not validate a200Mbps over-the-air ceiling'}
  (folder/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
