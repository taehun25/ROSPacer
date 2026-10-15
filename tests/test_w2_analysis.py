import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from w2_analysis import f_windows

class DynamicPhaseTests(unittest.TestCase):
    def sample(self):
        pub={'measurement_started_ns':100000000000,'payload_bytes':1048576,'records':[{'seq':0,'publish_start_ns':119000000000,'publish_succeeded':True}]}
        sub={'records':[{'seq':0,'publisher_wall_ns':1019000000000,'arrival_wall_ns':1021000000000}]}
        return pub,sub
    def test_delayed_message_is_assigned_to_publication_phase_for_latency(self):
        pub,sub=self.sample();out=f_windows(pub,sub,1000000000000,clock_validated=True)
        self.assertEqual(out[0]['publish_succeeded'],1)
        self.assertEqual(out[0]['p99_latency_of_messages_originating_in_phase_ms'],2000)
        self.assertEqual(out[0]['arrival_window_goodput_Mbps'],0)
        self.assertGreater(out[1]['arrival_window_goodput_Mbps'],0)
    def test_unqualified_clock_excludes_cross_host_phase_metrics(self):
        pub,sub=self.sample();out=f_windows(pub,sub,1000000000000)
        self.assertIsNone(out[0]['p99_latency_of_messages_originating_in_phase_ms'])
        self.assertIsNone(out[1]['arrival_window_goodput_Mbps'])
    def test_p99_uses_fractional_quantile_with_multiple_arrivals(self):
        pub,sub=self.sample();sub['records'].append({'seq':1,'publisher_wall_ns':1018000000000,'arrival_wall_ns':1018100000000})
        out=f_windows(pub,sub,1000000000000,clock_validated=True)
        self.assertAlmostEqual(out[0]['p99_latency_of_messages_originating_in_phase_ms'],1981)
