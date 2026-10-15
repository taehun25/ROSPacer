"""Restore the verified automatic TX-power policy after a finite experiment."""
import argparse,json,os,subprocess,time
from pathlib import Path
def run(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=8)
    if q.returncode:raise RuntimeError(q.stderr)
    return q.stdout
def restore(folder):
    b=json.loads((folder/'baseline.json').read_text());run(['iw','dev','wlp2s0','set','txpower','auto']);r={'restored_auto_policy':True,'info_after':run(['iw','dev','wlp2s0','info']),'before':b};(folder/'restoration.json').write_text(json.dumps(r,indent=2));return r
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','guard','end']);p.add_argument('--folder',required=True);a=p.parse_args();folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:raise ValueError('owned path/root required')
    if a.mode=='begin':
        if run(['nmcli','-g','802-11-wireless.tx-power','connection','show','iptime5GAX1500']).strip()!='0':raise ValueError('preserve non-auto configured power')
        folder.mkdir(parents=True,exist_ok=False);(folder/'baseline.json').write_text(json.dumps({'policy':'automatic NM tx-power0','info':run(['iw','dev','wlp2s0','info']),'regulatory':run(['iw','reg','get'])}))
        q=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'ready':True,'pid':q.pid,'expiry_s':21600}));return
    if a.mode=='guard':
        end=time.monotonic()+21600
        while time.monotonic()<end and not (folder/'end').exists():time.sleep(1)
        restore(folder);return
    (folder/'end').write_text('end');print(json.dumps(restore(folder)))
if __name__=='__main__':main()
