import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/"tools/lab_preflight.py"
spec = importlib.util.spec_from_file_location("lab_preflight", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Readiness(unittest.TestCase):
    def test_unreachable_hosts_never_appear_ready(self):
        findings = module.assess({"12": {"connection_error": "not connected"}})
        blocked = [f["host"] for f in findings
                   if f["gate"] == "remote_access" and f["status"] == "blocked"]
        self.assertEqual(blocked, ["12", "10"])

    def test_other_channel_counters_do_not_enable_adaptive(self):
        report = dict(survey={"stdout": "Survey data from wlo1\nfrequency: 5180 MHz\n"
                              "channel active time: 100 ms\nchannel busy time: 50 ms\n"
                              "channel transmit time: 10 ms\n"})
        finding = next(f for f in module.assess({"12": report})
                       if f["host"] == "12" and f["gate"] == "airtime_fields")
        self.assertEqual(finding["status"], "blocked")

    def test_present_counters_still_need_validation(self):
        report = dict(survey={"stdout": "Survey data from wlo1\nfrequency: 5180 MHz [in use]\n"
                              "channel active time: 100 ms\nchannel busy time: 50 ms\n"
                              "channel transmit time: 10 ms\n"})
        finding = next(f for f in module.assess({"12": report})
                       if f["host"] == "12" and f["gate"] == "airtime_fields")
        self.assertEqual(finding["status"], "needs_validation")

    def test_busy_process_and_version_mismatch_are_visible(self):
        base = dict(processes={"exit_code": 0}, packages={"exit_code": 0, "stdout": "2.6.10"})
        other = dict(base, packages={"exit_code": 0, "stdout": "2.6.11"})
        findings = module.assess({"12": base, "10": other})
        self.assertTrue(any(f["gate"] == "experiment_idle" and f["status"] == "blocked"
                            for f in findings))
        self.assertTrue(any(f["gate"] == "fastdds_versions" and f["status"] == "blocked"
                            for f in findings))


if __name__ == "__main__":
    unittest.main()
