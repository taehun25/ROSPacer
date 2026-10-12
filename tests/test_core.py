import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from rospacer.model import synthesize, quantity, adaptive_rate, identify_overhead, golden_profile
from rospacer.profiles import fastdds, cyclone, validate
from rospacer.linux import deltas
from rospacer.linux import govern


class OperatingPoints(unittest.TestCase):
    def test_uncalibrated_golden_never_enables_governor(self):
        cfg = golden_profile()
        self.assertIsNone(cfg['capacity_Bps'])
        self.assertFalse(cfg['feasible_recovery'])
        with patch('rospacer.linux.Shaper') as shaper:
            with self.assertRaisesRegex(ValueError, 'golden is uncalibrated'):
                govern(cfg, 'fixed', 1, 'unused.csv')
            shaper.assert_not_called()

    def test_recovery_budget_with_paced_cap(self):
        p = synthesize(1048576, 10, 1, 25000000, .004, 1)
        # Proposal's 13 MiB example exceeds tau*(0.9C-L).
        self.assertEqual(p["cache_upper_bytes"], 12014240)
        self.assertTrue(p["feasible_recovery"])
        self.assertLessEqual(p["cache_bytes"], p["cache_upper_bytes"])
        self.assertGreaterEqual(p["cache_bytes"], p["cache_lower_bytes"])

    def test_overload_is_explicit(self):
        p = synthesize(1048576, 80, 3, 25000000, .004, 1)
        self.assertFalse(p["feasible_recovery"])
        self.assertEqual(p["cache_samples"], 2)
        self.assertGreater(p["rho"], 1)

    def test_discrete_cache_interval(self):
        p = synthesize(1048576, 10, 1, 25000000, .004, .23)
        self.assertFalse(p["feasible_recovery"])

    def test_units(self):
        self.assertEqual(quantity("200Mbps", "rate"), 25000000)
        self.assertEqual(quantity("1MiB", "bytes"), 1048576)
        self.assertEqual(quantity("4ms", "time"), .004)
        for value in ("nan", "-1MB", "0B", "100MHz"):
            with self.assertRaises(ValueError):
                quantity(value, "bytes")

    def test_airtime_calibration_and_competition(self):
        cfg = synthesize(1048576, 10, 1, 25000000, .004, 1)
        cfg["airtime_overhead_s"] = identify_overhead(25000000, 100000000,
                                                     100000000, .1, 1472, 64)
        d = dict(elapsed_s=.2, busy_s=.1, tx_s=.02, tx_Bps=100000000,
                 rx_Bps=100000000, retries=10, packets=100, bytes=100000)
        clean = adaptive_rate(cfg, dict(d, busy_s=.02), False)
        busy = adaptive_rate(cfg, d, False)
        self.assertAlmostEqual(clean["cap_application_Bps"], 22500000)
        self.assertLess(busy["cap_application_Bps"], clean["cap_application_Bps"])

    def test_counter_reset_and_missing_survey(self):
        old = dict(adaptive_ready=True, monotonic_s=1, active_s=1, busy_s=.5,
                   tx_s=.1, bytes=100, packets=10, retries=1, tx_Bps=1, rx_Bps=1)
        new = dict(old, monotonic_s=1.2, active_s=1.2, busy_s=.6, bytes=200)
        self.assertAlmostEqual(deltas(old, new)["elapsed_s"], .2)
        with self.assertRaises(ValueError):
            deltas(old, dict(new, bytes=0))
        with self.assertRaises(ValueError):
            deltas(old, dict(new, adaptive_ready=False))

    def test_missing_driver_counters_prevents_system_mutation(self):
        cfg = synthesize(1048576, 10, 1, 25000000, .004, 1)
        cfg.update(dev="wlo1", airtime_overhead_s=.00001, relay_in_survey=False)
        with patch("rospacer.linux.observe", return_value={"adaptive_ready": False}), \
                patch("rospacer.linux.Shaper") as shaper:
            with self.assertRaisesRegex(RuntimeError, "driver lacks"):
                govern(cfg, "adaptive", 1, "unused.csv")
            shaper.assert_not_called()

    def test_cyclone_schema(self):
        cfg = synthesize(1048576, 10, 1, 25000000, .004, 1)
        schema = Path(__file__).resolve().parents[1]/"reference/cyclonedds-0.10.5.xsd"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"cyclone.xml"
            cyclone(cfg, path, "wlo1", "192.168.0.4")
            self.assertTrue(validate(path, schema))

    def test_unqualified_survey_semantics_prevents_system_mutation(self):
        cfg=synthesize(1048576,10,1,25000000,.004,1)
        cfg.update(dev='wlp2s0',airtime_overhead_s=.00001,relay_in_survey=True)
        with patch('rospacer.linux.observe',return_value={'adaptive_ready':True}),patch('rospacer.linux.Shaper') as shaper:
            with self.assertRaisesRegex(RuntimeError,'semantics have not passed'):
                govern(cfg,'adaptive',1,'unused.csv')
            shaper.assert_not_called()

    def test_cyclone_fragment_budget_covers_directed_repair(self):
        import xml.etree.ElementTree as E
        for overhead in [64, 128]:
            cfg = synthesize(1048576, 10, 1, 25000000, .004, 1, header=overhead)
            with tempfile.TemporaryDirectory() as d:
                path = Path(d)/"cyclone.xml"
                cyclone(cfg, path, "wlo1", "192.168.0.4")
                text = E.parse(path).find('.//{https://cdds.io/config}FragmentSize').text
                fragment = int(text.split()[0])
                # IPv4+UDP28, RTPS20, INFO_TS12, INFO_DST16, DATA_FRAG36.
                # Initial-only68-byte framing missed the directed repair path.
                self.assertLessEqual(fragment + max(overhead, 20+12+16+36) + 28, cfg['mtu'])
                self.assertEqual(fragment % 4, 0)

    def test_fastdds_locally_corrected_schema(self):
        cfg = synthesize(1048576, 10, 1, 25000000, .004, 1)
        schema = Path(__file__).resolve().parents[1]/"reference/fastdds-2.6.10-local-validation.xsd"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"fastdds.xml"
            fastdds(cfg, path, "192.168.0.3")
            self.assertTrue(validate(path, schema))


if __name__ == "__main__":
    unittest.main()
