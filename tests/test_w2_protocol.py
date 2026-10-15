import unittest,tempfile,xml.etree.ElementTree as E
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from w2_protocol import matrix,topology,profile,topic_name,competition_schedule,ScopeError
from rospacer.model import synthesize

class W2ProtocolTests(unittest.TestCase):
    def test_every_planned_topic_and_retry_is_valid_and_unique(self):
        import re
        topics=[topic_name(r['id']+suffix,sender) for r in matrix() for suffix in ['', '__a001','__a002'] for sender in [None,'4','5']]
        self.assertEqual(len(topics),len(set(topics)))
        self.assertTrue(all(re.fullmatch(r'/[A-Za-z_][A-Za-z0-9_]*',s) for s in topics))
        self.assertNotEqual(topic_name('P0_low_0.6'),topic_name('P0_low_0_6'))
    def test_scope_exception_has_one_identity_when_runner_is_imported(self):
        import w2_runner
        self.assertIs(ScopeError,w2_runner.ScopeError)
    def test_competition_phases_use_separate_server_ports(self):
        phases=competition_schedule('F',80)
        self.assertEqual([p['factor'] for p in phases],[0,.5,.9,0])
        self.assertNotEqual(phases[1]['port'],phases[2]['port'])
        b2=competition_schedule('B2',60);ports=[p['port'] for p in b2 if p['factor']!=0]
        self.assertEqual(len(ports),15);self.assertEqual(len(set(ports)),15)
    def test_matrix_order_and_repetitions(self):
        rows=matrix();self.assertEqual(len(rows),207);self.assertEqual(len({r['id'] for r in rows}),207)
        self.assertEqual({r['rep'] for r in rows},{1,2,3})
        stages=[r['stage'] for r in rows];self.assertEqual(stages[:33],['T1_E']*33);self.assertEqual(stages[33:66],['T1_F']*33);self.assertEqual(stages[66:99],['T3_E']*33)
        self.assertEqual(stages[-18:],['P0_B2']*18)
    def test_t3_is_two_publishers_each_with_two_receivers(self):
        pubs,subs=topology('T3');self.assertEqual(pubs,['4','5']);self.assertEqual(subs,['12','10']);self.assertFalse(set(pubs)&set(subs))
    def test_vendor_really_selects_tcp(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'vendor.xml';cfg=synthesize(1048576,10,1,40e6,.01,1)
            profile(cfg,'fastdds','vendor',p,'wlp2s0','192.168.0.4',['192.168.0.5'],55624,[55625])
            xml=p.read_text();self.assertIn('TCPv4',xml);self.assertIn('55625',xml);self.assertIn('PREALLOCATED_WITH_REALLOC',xml)
            self.assertNotIn('max_samples',xml)
    def test_default_keeps_fragment_and_cache_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'default.xml';cfg=synthesize(1048576,10,1,40e6,.01,1)
            profile(cfg,'cyclonedds','default',p,'wlp2s0','192.168.0.4',['192.168.0.5']);xml=p.read_text()
            self.assertNotIn('MaxMessageSize',xml);self.assertNotIn('Watermarks',xml);self.assertIn('NetworkInterface',xml)
    def test_overload_cannot_claim_recovery_feasible(self):
        cfg=synthesize(1048576,1.5*40e6/1048576,1,40e6,.01,1);self.assertFalse(cfg['feasible_recovery']);self.assertEqual(cfg['cache_samples'],2)

if __name__=='__main__':unittest.main()
