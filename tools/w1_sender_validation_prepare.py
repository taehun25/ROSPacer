"""Freeze qualification criteria and finite unattended sleep guards."""
import json
import subprocess
import sys
from deploy import ROOT,REMOTE
from w1_b2 import Control
def main():
    base=ROOT/'runs/w1_20261013_sender_validation';c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',base);c.bind='192.168.0.11';r={}
    for h,user in [('4','csilab'),('5','csi')]:
        folder='/home/'+user+'/'+REMOTE+'/runs/'+base.name
        r[h]=c.python(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(folder)+");q=subprocess.Popen(['sudo','-n','timeout','-k','2','21600','systemd-inhibit','--what=sleep:idle','--mode=block','--who=ROSPacer','--why=FiniteSenderValidation','sleep','21590'],stdin=subprocess.DEVNULL,stdout=open(p/'inhibit.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    q=subprocess.Popen([sys.executable,str(ROOT/'tools/w1_local_awake.py'),'--folder',str(base)],stdin=subprocess.DEVNULL,stdout=open(base/'local_awake.log','w'),stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);r['PC']={'pid':q.pid}
    (base/'inhibitors.json').write_text(json.dumps(r,indent=2))
    profile=ROOT/'runs/w1_20261013_sender_only/frozen_sender_profile_v2.json'
    (base/'frozen_profile.json').write_bytes(profile.read_bytes())
    p={'date':'2026-10-13','profile':'frozen_profile.json','refit':False,'online_input':'source4 only; receiver5 counters are offline reference, never controller input','period_s':.2,'window_s':3,'minimum_window_s':2,
       'sufficiency':{'eligible_steady_window_success_fraction_min':.95,'body_coverage':[.8,1.1],'capture_drops':0,'unknown_PHY_bytes':0,'downlink_Mbps':[1195,1205]},
       'self_beta_abs_p95_max':.05,'capacity_relative_error_max':.20,
       'capacity_units':'Unclipped (1-beta)/theta station-byte budget * UDP1400/mean_station_bytes vs receiver payload goodput; clipped HTB ceiling is not raw capacity.',
       'stability':{'reconnect_allowed_but_does_not_count_as_pass':True,'noqueue_restored':True,'monitor_removed':True,'ordinary_wifi_ping_and_ssh_restored':True},
       'tests':['self0.2/0.5/0.8 repeats','B2 other AP','C2 same AP if background10 prepared','Fast/Cyclone1MiB shadow','missing/AP/reset/cleanup gate tests'],
       'HTB':'No automatic shaping until all frozen-profile qualification passes; failures and holds retained.'}
    (base/'protocol.json').write_text(json.dumps(p,indent=2))
    print(json.dumps({'criteria_frozen':True,'sleep_guards':list(r)}))
if __name__=='__main__':main()
