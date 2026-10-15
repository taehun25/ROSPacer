"""New execution segment; original successful data and failed attempts stay immutable."""
import json,sys,shutil,shlex,time
from pathlib import Path
from deploy import ROOT
from w2_control import Lab,OTHER,SR2,HOSTS
from w2_runner import Runner,write
from w2_protocol import matrix,topic_name
from rospacer.sender_minphy import require_qualification

OLD=ROOT/'runs/w2_20261014_3rep'
BASE=ROOT/'runs/w2_20261015_resume1'

def initialise():
    if len(sys.argv)>1 and sys.argv[1]=='finish':return finish_preparation(Runner(BASE))
    prior=json.loads((OLD/'results.json').read_text(encoding='utf-8'))
    for name in ['calibration_t1','validation_t1_Clean','calibration_t3_4','calibration_t3_5']:
        shutil.copytree(OLD/name,BASE/name,dirs_exist_ok=True)
    for name in ['runtime_manifest.json','T3_calibration.json','smoke_ready.json','extended_smoke_ready.json','final_paths_ready.json']:
        shutil.copy2(OLD/name,BASE/name)
    retained=[];excluded=[]
    for z in prior:
        scope=z['row']['topology']=='T3' and z['row']['mode']=='adaptive' and z.get('reason','').startswith('T3 Adaptive blocked:')
        keep=z['status']=='measured' and z['row']['condition']!='F'
        if keep or scope:
            data={**z,'source_artifacts_root':str(OLD/'trials'/z['id']),'inherited_from':str(OLD)}
            if scope:data.update(status='blocked_scope',original_recorded_status=z['status'],classification_correction='shared ScopeError module identity fixed; independent budget gate unchanged')
            write(BASE/'trials'/z['id']/'summary.json',data);retained.append(data)
        else:excluded.append({'id':z['id'],'status':z['status'],'reason':z.get('reason'),'source':str(OLD/'trials'/z['id'])})
    write(BASE/'continuation.json',{'predecessor':str(OLD),'retained_measured':sum(z['status']=='measured' for z in retained),'retained_scope_gates':6,'rerun_all_F':True,'reason':'phase ports isolated and scheduled independently; use a consistent corrected F generator for all modes/repetitions','excluded_from_new_primary':excluded,'original_data_changed':False,'started_KST':time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(time.time()+9*3600))})
    write(BASE/'results.json',retained)
    lab=Lab(BASE);lab.direct4=False;sessions={}
    for ap,hosts in [(OTHER,['5','4']),(SR2,['12','10'])]:
        lab.select(ap)
        for h in hosts:
            code='import json,subprocess;from pathlib import Path;p=subprocess.run(["pgrep","-af",'+repr(r'[w]2_traffic.py|[w]2_worker.py|[s]ender-govern|[i]perf3 -(c|s)|[r]un_sweep')+'],capture_output=True,text=True);print(json.dumps({"rc":p.returncode,"processes":p.stdout,"mac":Path("/sys/class/net/'+HOSTS[h][3]+'/address").read_text().strip()}))'
            check=lab.py(h,code)
            if check['rc']!=1 or check['mac']!=HOSTS[h][4]:raise RuntimeError('host identity/activity check failed '+h+str(check))
            home=lab.home(h);folder=home+'/runs/'+BASE.name+'/session'
            lab.put(h,home+'/tools/w2_host_guard.py',(ROOT/'tools/w2_host_guard.py').read_bytes())
            d=json.loads(lab.ssh(h,shlex.join(['python3',home+'/tools/w2_host_guard.py','begin','--folder',folder,'--host',h]),root=True,timeout=85));d['folder']=folder;sessions[h]=d;write(BASE/'sessions.json',sessions);print('prepared '+h,flush=True)
            if h=='4':lab.wired=True
    write(BASE/'pair_ap.json',{'ap':SR2});lab.select(OTHER)
    r=Runner(BASE);r.deploy();finish_preparation(r)

def finish_preparation(r):
    r.lab.select(OTHER)
    # Verify every generated topic with the installed Humble validator before a
    # single measured process is dispatched; exercise retry and T3 names too.
    topics=[topic_name(x['id']+suffix,sender) for x in matrix() for suffix in ['', '__a001', '__a002'] for sender in [None,'4','5']]
    source='import json;from rclpy.validate_topic_name import validate_topic_name\nnames='+repr(topics)+'\nfor name in names:validate_topic_name(name)\nprint(json.dumps({"validated_topics":len(names)}))'
    proof=json.loads(r.lab.ssh('4',shlex.join(['bash','-c','source /opt/ros/humble/setup.bash; exec python3 -']),source.encode(),timeout=40))
    write(BASE/'topic_validation.json',proof)
    for h in ['4','5']:
        r.lab.ssh(h,'sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304',root=True)
        r.lab.ssh(h,'iw dev wlp2s0 set power_save off',root=True)
    # Do not refit the old model against its held-out observations. Check the
    # frozen profile against today's independent Clean measurement.
    bundle=r.folder('4','calibration_t1')
    for name in ['profile.json','manifest.json']:r.put('4',bundle+'/'+name,(BASE/'calibration_t1'/name).read_bytes())
    out=r.folder('4','resume_clean_validation')
    argv=['sudo','-n','python3','-m','rospacer','sender-validate','--dev','wlp2s0','--source','192.168.0.4','--peer','192.168.0.5','--peer-ssh','csi@192.168.0.5','--ssh-key','/home/csilab/.ssh/id_ed25519_rospacer_cal','--known-hosts','/home/csilab/.ssh/rospacer_cal_known_hosts','--host-key-alias','192.168.0.5','--out',out,'--bundle',bundle,'--condition','Clean','--socket-bytes','1048576','--seconds','15']
    job=r.launch('4','command','resume_clean_validation_job',argv,timeout=85)
    done=r.wait('4',job,100);r.archive('4',job,BASE/'resume_clean_validation_job');r.archive('4',out,BASE/'resume_clean_validation')
    if done['rc']:raise RuntimeError('fresh frozen-profile validation failed to execute')
    require_qualification(BASE/'calibration_t1/profile.json',[BASE/'resume_clean_validation/validation.json'])
    v=json.loads((BASE/'resume_clean_validation/validation.json').read_text());p=json.loads((BASE/'calibration_t1/profile.json').read_text());ratio=v['receiver_phy_calibrated']['measured_Mbps']/(p['capacity_payload_Bps']*8/1e6)
    write(BASE/'capacity_continuity.json',{'ratio_to_original_C0':ratio,'within_10_percent':.9<=ratio<=1.1,'independent_validation':v['receiver_phy_calibrated']})
    if not .9<=ratio<=1.1:raise RuntimeError('fresh C0 differs >10%; new calibration stratum required before pooling')
    # Keep the original independent validation and add today's proof alongside it.
    write(BASE/'prelaunch.json',{'passed':True,'validated_topics':proof['validated_topics'],'source_scope_and_fresh_Clean_passed':True,'capacity_continuity':ratio,'requires_resume_smoke':True})
    r.cleanup_trial();r.status('prepared_resume',retained_measured=59,pending_planned=142)
    print(json.dumps({'prepared':True,'topic_validation':proof,'capacity_ratio':ratio}),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');initialise()
