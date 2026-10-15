import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

from rospacer.sender_minphy import evaluate, interval_rate, require_qualification, step


class SenderMinphyTests(unittest.TestCase):
    def test_sender_benchmark_entrypoint_from_unrelated_directory(self):
        script = Path(__file__).resolve().parents[1]/'tools/w1_sender_local_smoke.py'
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([sys.executable, str(script), '--help'], cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('--bundle', p.stdout)

    def test_server_zero_end_uses_nonzero_intervals(self):
        server = {'end': {'sum': {'bytes': 0}}, 'intervals': [{'streams': [{'seconds': 2, 'bytes': 8000}]}]}
        self.assertEqual(interval_rate(server), 4000)
        with self.assertRaises(ValueError):
            interval_rate({'intervals': []})

    def test_qualification_rejects_changed_profile_or_failed_budget(self):
        with tempfile.TemporaryDirectory() as d:
            profile = Path(d)/'profile.json'; profile.write_text('{}')
            validation = Path(d)/'validation.json'
            from rospacer.sender_minphy import digest
            r = {'condition': 'Clean', 'profile_sha256': digest(profile), 'receiver_phy_calibrated': {'passed': True,
                 'predicted_Mbps':100, 'measured_Mbps':100, 'eligible_windows':100, 'valid_windows':100,
                 'relative_error':0., 'usable_fraction':1.}}
            validation.write_text(json.dumps(r))
            self.assertEqual(require_qualification(profile, [validation]), ['Clean'])
            profile.write_text('{"changed":true}')
            with self.assertRaises(ValueError): require_qualification(profile, [validation])
            profile.write_text('{}'); r['receiver_phy_calibrated']['passed'] = False
            validation.write_text(json.dumps(r))
            with self.assertRaises(ValueError): require_qualification(profile, [validation])
            r['receiver_phy_calibrated'].update(passed=True, predicted_Mbps=130)
            validation.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'inconsistent'):require_qualification(profile,[validation])

    def test_step_does_not_substitute_missing_counters_or_bridge_new_ap(self):
        profile = {'AP': 'a'}
        rows = [{'monotonic_s': 0, 'boot_id': 'boot', 'AP': 'a'}, {'monotonic_s': 3, 'boot_id': 'boot', 'AP': 'b'}]
        with self.assertRaisesRegex(ValueError, 'AP changed'): step(profile, rows, 'boot', 3)
        rows[-1]['AP'] = 'a'
        with self.assertRaisesRegex(ValueError, 'stale'): step(profile, rows, 'boot', 5)
        with self.assertRaisesRegex(ValueError, 'gap'): step(profile, rows, 'boot', 3)
        rows = [{'monotonic_s': i, 'boot_id': 'boot', 'AP': 'a'} for i in range(4)]
        with self.assertRaises(KeyError): step(profile, rows, 'boot', 3)
        profile['frequency_MHz'] = 5745; rows[-1]['frequency_MHz'] = 5180
        with self.assertRaisesRegex(ValueError, 'channel changed'): step(profile, rows, 'boot', 3)

    def test_input_ablation_does_not_refit_coefficients(self):
        profile = {'peer_rx_phy_Bps': 10, 'service_effective_overhead_s': 7}
        trial = {'rows': [], 'start_monotonic': 0, 'end_monotonic': 10, 'receiver_payload_Bps': 12500000}
        a = {}; b = {'window_tx_Bps': 20}
        seen = []
        def estimator(p, old, new):
            seen.append(dict(p)); return {'raw_UDP_payload_Mbps': 100, 'beta': .1}
        with patch('rospacer.sender_minphy.windows', return_value=[(a, b)]), patch('rospacer.sender_minphy.estimate', side_effect=estimator):
            result = evaluate(profile, trial)
        self.assertEqual([p['peer_rx_phy_Bps'] for p in seen], [10, 20])
        self.assertEqual([p['service_effective_overhead_s'] for p in seen], [7, 7])
        self.assertEqual(profile['peer_rx_phy_Bps'], 10)
        self.assertTrue(result['receiver_phy_calibrated']['passed'])


if __name__ == '__main__': unittest.main()
