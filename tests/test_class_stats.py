import unittest
from rospacer.linux import parse_class_stats


class ClassCounters(unittest.TestCase):
    def test_ubuntu_text_counters_remain_distinct(self):
        raw = ("class htb 7ac0:10 root leaf 7ac1: prio 0 rate 19176Kbit\n"
               " Sent 123456 bytes 100 pkt (dropped 2, overlimits 0 requeues 0)\n"
               " backlog 0b 0p requeues 0\n"
               "class htb 7ac0:20 root prio 0 rate 10Gbit\n"
               " Sent 999 bytes 4 pkt (dropped 0, overlimits 0 requeues 0)\n")
        result = parse_class_stats(raw)
        self.assertEqual([(r["handle"],r["bytes"],r["drops"]) for r in result],
                         [("7ac0:10",123456,2),("7ac0:20",999,0)])
        self.assertIn("19176Kbit",result[0]["raw"])

    def test_json_and_unknown_output(self):
        self.assertEqual(parse_class_stats('[{"handle":"7ac0:10","bytes":12}]')[0]["bytes"],12)
        self.assertEqual(parse_class_stats(''),[])
        with self.assertRaises(RuntimeError):
            parse_class_stats("unsupported unexpected output")


if __name__ == "__main__":
    unittest.main()
