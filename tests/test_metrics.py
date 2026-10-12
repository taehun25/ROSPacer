import unittest

from rospacer.metrics import analyze_pair


class PairedMetrics(unittest.TestCase):
    def test_backpressure_does_not_hide_missing_offered_samples(self):
        pub = dict(role="pub", requested=4, payload_bytes=1000, requested_hz=10,
                   records=[dict(seq=i, publish_succeeded=True, publish_start_ns=i*1000000000,
                                 publish_duration_ms=300) for i in (0,1)])
        sub = dict(role="sub", records=[dict(seq=i, arrival_monotonic_ns=i*1000000000) for i in (0,1)])
        d = analyze_pair(pub,sub)
        self.assertEqual(d["delivery_requested"], .5)
        self.assertEqual(d["delivery_successful_publish"], 1)
        self.assertEqual(d["actual_publish_hz"], 1)
        self.assertEqual(d["arrival_interval_goodput_Bps"],1000)
        self.assertIsNone(d["end_to_end_latency_ms"])

    def test_failed_publish_can_still_have_received_data(self):
        pub = dict(role="pub", requested=2, records=[dict(seq=0,publish_succeeded=True),
                                                    dict(seq=1,publish_succeeded=False)])
        sub = dict(role="sub", records=[dict(seq=i,arrival_monotonic_ns=j) for j,i in enumerate((0,1,1,9))])
        d = analyze_pair(pub,sub)
        self.assertEqual(d["received_without_success"],[1])
        self.assertEqual(d["publish_failed"],1)
        self.assertEqual(d["duplicate_arrivals"],1)
        self.assertEqual(d["received_out_of_range"],[9])
        self.assertEqual(d["unique_received"],2)

    def test_one_or_zero_samples_do_not_invent_rates(self):
        pub = dict(role="pub",requested=1,records=[])
        sub = dict(role="sub",records=[])
        d = analyze_pair(pub,sub)
        self.assertIsNone(d["actual_publish_hz"])
        self.assertIsNone(d["delivery_successful_publish"])
        self.assertEqual(d["delivery_requested"],0)
        self.assertIsNone(d["publish_duration_ms"]["p95"])

    def test_roles_are_checked(self):
        with self.assertRaises(ValueError):
            analyze_pair(dict(role="sub"),dict(role="sub"))

    def test_latency_requires_bounded_clock_and_complete_timestamps(self):
        pub=dict(role='pub',requested=1,records=[dict(seq=0)])
        sub=dict(role='sub',records=[dict(seq=0,arrival_monotonic_ns=1,arrival_wall_ns=2000000,publisher_wall_ns=1000000)])
        self.assertIsNone(analyze_pair(pub,sub)['end_to_end_latency_ms'])
        evidence=dict(validated=True,relative_error_bound_ms=.08)
        self.assertEqual(analyze_pair(pub,sub,evidence)['end_to_end_latency_ms']['p50'],1)
        sub['records'][0]['publisher_wall_ns']=5000000
        self.assertFalse(analyze_pair(pub,sub,evidence)['clock_validated'])
        with self.assertRaises(ValueError):
            analyze_pair(pub,sub,dict(validated=True,relative_error_bound_ms=2))


if __name__ == "__main__":
    unittest.main()
