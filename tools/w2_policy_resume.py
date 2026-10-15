"""One-time safe-boundary handoff to the case-isolation failure policy."""
import json,shlex,shutil,sys,time
from deploy import ROOT
from w2_runner import Runner,write
from w2_control import Lab,OTHER,SR2

BASE=ROOT/'runs/w2_20261015_resume1'

def main():
    progress=json.loads((BASE/'progress.json').read_text())
    if progress['state']!='stopped' or progress.get('reason')!='user STOP marker':
        raise RuntimeError('prior coordinator must finish its current case and stop first')
    restored=json.loads((BASE/'restoration.json').read_text())
    if not all(restored.get(h,{}).get('restored') for h in ['4','5','12','10']):
        raise RuntimeError('prior full restoration must be verified first')
    hist=BASE/'segment_history/failure_policy'
    for name in ['progress.json','results.json','restoration.json','runner.stdout.log','runner.stderr.log']:
        shutil.copy2(BASE/name,hist/('boundary_'+name))
    lab=Lab(BASE);lab.direct4=False;sessions={}
    for ap,hosts in [(OTHER,['5','4']),(SR2,['12','10'])]:
        lab.select(ap)
        for h in hosts:
            home=lab.home(h);folder=home+'/runs/'+BASE.name+'/session_policy'
            lab.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
            value=json.loads(lab.ssh(h,shlex.join(['python3',home+'/tools/w2_host_guard.py','begin','--folder',folder,'--host',h]),root=True,timeout=85))
            value['folder']=folder;sessions[h]=value;write(BASE/'sessions.json',sessions)
            print('rearmed '+h,flush=True)
            if h=='4':lab.wired=True
    write(BASE/'pair_ap.json',{'ap':SR2})
    runner=Runner(BASE);runner.deploy();runner.ap_pair(OTHER)
    runner.active='policy_preflight';runner.active_artifact='policy_preflight'
    proof=runner.verify_case_isolation()
    if not proof['passed']:raise RuntimeError('new policy environmental audit failed')
    write(BASE/'failure_policy.json',{
        'version':2,'passed':True,'max_attempts_per_case_per_invocation':2,
        'case_failure':'retain all attempts, mark skipped_failed, continue if environment audit passes',
        'shared_environment_failure':'two bounded cleanup/audit rounds, then halt and restore',
        'performance':'low delivery or throughput is a valid measurement; do not retry',
        'terminal_statuses':['measured','blocked_scope','skipped_failed'],
        'preflight_evidence':'trials/policy_preflight/case_isolation.json',
        'previous_case_finished':progress['active'],'retained_measured':progress['valid_measured'],
        'wall':time.time()})
    (BASE/'STOP').rename(hist/'boundary_STOP.txt')
    runner.freeze_sources();runner.active=None;runner.status('resume_ready',failure_policy_version=2)
    print('case-isolation policy ready',flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
