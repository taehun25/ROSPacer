"""Recover summary for a remotely completed run whose collection lost SSH."""
import json,sys
from deploy import ROOT
from w1_backpressure import analyze_telemetry
sys.path.insert(0,str(ROOT))
from rospacer.metrics import analyze_pair

def main():
    base=ROOT/'runs/w1_20261012_163000';name='cyclonedds_vendor_retry';folder=base/name
    pub=json.loads((folder/'12/pub.json').read_text());sub=json.loads((folder/'10/sub.json').read_text());cfg=json.loads((folder/'12/config.json').read_text())
    summary={'name':name,'rmw':'cyclonedds','label':'vendor','metrics':analyze_pair(pub,sub),'config':cfg,
      'telemetry':{h:analyze_telemetry(folder/h/'telemetry.jsonl') for h in ['12','10']},'shaped':False,'clock_validated':False,
      'vendor_definition':'Native Cyclone fragmentation/WHC;1MiB send/10MiB receive socket tuning',
      'recovered_after_controller_disconnect':True,'command_return_code':None,'source_commit':'5abaeb3'}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps({'name':name,'metrics':summary['metrics']}))

if __name__=='__main__':main()
