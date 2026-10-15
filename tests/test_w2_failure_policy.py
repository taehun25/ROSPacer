import unittest,sys,os,json,tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from w2_failure_policy import decide,summarize_record,TERMINAL

class FailurePolicyTests(unittest.TestCase):
    def test_isolated_failures_do_not_stop_later_cases(self):
        outcomes=[]
        for _ in range(4):
            self.assertEqual(decide('failed',True,1),'retry')
            decision=decide('failed',True,2)
            outcomes.append(summarize_record({'status':'failed','reason':'invalid topic'},decision))
        self.assertTrue(all(x['status']=='skipped_failed' for x in outcomes))
        self.assertTrue(all(x['status'] in TERMINAL for x in outcomes))
        self.assertEqual(decide('measured',True,1),'continue')
    def test_shared_environment_failure_halts_even_after_good_measurement(self):
        for status in ['failed','measured','blocked_scope']:
            self.assertEqual(decide(status,False,1),'halt')
    def test_bad_performance_is_valid_without_retry(self):
        row={'status':'measured','published':100,'received':0,'goodput_Mbps':0}
        action=decide(row['status'],True,1)
        self.assertEqual(action,'continue');self.assertEqual(summarize_record(row,action),row)
    def test_skip_preserves_failure_reason_and_original_outcome(self):
        row={'status':'impairment_unqualified','reason':'UDP phase missing','artifact_id':'case__a002'}
        result=summarize_record(row,'skip')
        self.assertEqual(result['original_status'],row['status'])
        self.assertEqual(result['reason'],row['reason'])
        self.assertEqual(row['status'],'impairment_unqualified')

@unittest.skipUnless(os.name=='nt','The campaign entry point uses Windows kernel locks')
class CampaignPolicyTests(unittest.TestCase):
    def run_campaign(self, healthy=True):
        import w2_runner as module
        events=[]
        class FakeRunner:
            def __init__(self,base):
                self.base=Path(base);self.results=[];self.failures=0;self.active=None;self.current_row=None
            def freeze_sources(self):pass
            def trial(self,row):
                self.active=row['planned_id'];events.append(('trial',self.active))
                if self.active!='case3':raise RuntimeError('before publisher start: case-specific configuration')
                return {'status':'measured','published':100,'received':0,'goodput_Mbps':0}
            def cleanup_trial(self):events.append(('cleanup',self.active))
            def verify_case_isolation(self):return {'passed':healthy}
            def status(self,state,**kw):events.append(('status',state))
            def restore(self):events.append(('restore',None));return {'passed':True}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'campaign';base.mkdir();(root/'runs').mkdir()
            for name in ['smoke_ready','extended_smoke_ready','final_paths_ready','prelaunch']:
                (base/(name+'.json')).write_text('{"passed":true}')
            rows=[{'id':'case'+str(i),'topology':'T1'} for i in range(4)]
            with patch.object(module,'Runner',FakeRunner),patch.object(module,'ROOT',root),patch.object(module,'matrix',return_value=rows),patch.object(sys,'argv',['runner','run','--base',str(base)]):
                if healthy:module.main()
                else:
                    with self.assertRaisesRegex(RuntimeError,'shared environment isolation failed'):module.main()
            results=json.loads((base/'results.json').read_text(encoding='utf-8'))
            attempts=json.loads((base/'trials/case0/attempts.json').read_text(encoding='utf-8'))
            return results,events,attempts
    def test_real_entry_point_skips_three_failed_cases_and_runs_next(self):
        rows,events,attempts=self.run_campaign()
        self.assertEqual([x['status'] for x in rows],['skipped_failed']*3+['measured'])
        self.assertEqual(len([e for e in events if e[0]=='trial']),7)
        self.assertEqual(len(attempts),2)
        self.assertEqual(rows[-1]['received'],0)
        self.assertIn(('status','finished_with_skipped_cases'),events)
    def test_real_entry_point_halts_if_shared_environment_is_not_restored(self):
        rows,events,attempts=self.run_campaign(False)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'environment_blocked')
        self.assertEqual(len(attempts),1)
        self.assertIn(('restore',None),events)
