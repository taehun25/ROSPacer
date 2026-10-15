"""Finite clean-repeat, DDS shadow and power-state transition diagnosis."""
import json,subprocess,sys
from deploy import ROOT
from w1_b2 import Control
BASE=ROOT/'runs/w1_20261013_sender_validation'
def main():
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',BASE);c.bind='192.168.0.11'
    subprocess.run([sys.executable,'tools/w1_sender_validate_run.py','--tag','clean_monitor_r2','--rate-mbps','0','--seconds','24'],cwd=ROOT,check=True)
    dds={}
    for rmw in ['fastdds','cyclonedds']:
        q=subprocess.run([sys.executable,'tools/w1_sender_smoke.py','--rmw',rmw,'--revision','validation'],cwd=ROOT)
        dds[rmw]={'orchestration_rc':q.returncode}
        # Recovery is possible over the still-owned wire even after a shadow failure.
        r=c.extra('5','timeout -k 1 8 ssh -o BatchMode=yes -o ConnectTimeout=3 -o HostKeyAlias=192.168.0.4 csilab@192.168.0.4 hostname')
        dds[rmw]['ordinary_wifi_ssh_rc']=r.returncode
        if r.returncode:
            z=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');dds[rmw]['reconnect_rc']=z.returncode
        print(json.dumps({'DDS_lifecycle':rmw,**dds[rmw]}),flush=True)
    (BASE/'dds_lifecycle.json').write_text(json.dumps(dds,indent=2))
    q=c.extra('4','sudo -n iw dev wlp2s0 set power_save on');assert q.returncode==0
    try:
        q=subprocess.run([sys.executable,'tools/w1_sender_validate_run.py','--tag','power_transition','--rate-mbps','66.766576484','--seconds','24'],cwd=ROOT)
        (BASE/'power_transition_orchestration.json').write_text(json.dumps({'rc':q.returncode,'purpose':'source power save on before monitor entry; CPU performance and enlarged buffers unchanged; separate lifecycle diagnosis'}))
    finally:
        q=c.extra('4','sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0
if __name__=='__main__':main()
