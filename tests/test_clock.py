import unittest
from rospacer.clock import qualify_pair


class ClockQualification(unittest.TestCase):
    def rows(self,label):
        tracking='System time     : 0.000001 seconds slow\nRoot delay      : 0.0001 seconds\nRoot dispersion : 0.000005 seconds\nLeap status     : Normal\n'
        if label=='5':tracking+='Reference ID    : 7F7F0101\n'
        return [dict(wall_ns=t,tracking=dict(stdout=tracking),sources=dict(stdout='^* 192.168.50.1 10'),ntpdata=dict(stdout='Remote address : 192.168.50.1\nLocal address : 192.168.50.2')) for t in [0,500000000,1000000000]]

    def test_wired_bounded_samples_qualify(self):
        self.assertTrue(qualify_pair(self.rows('4'),self.rows('5'),100000000,900000000)['validated'])

    def test_stale_or_wrong_source_does_not_qualify(self):
        self.assertFalse(qualify_pair(self.rows('4'),self.rows('5'),100000000,2000000000)['validated'])
        rows=self.rows('4');rows[1]['sources']['stdout']='^? 192.168.50.1 10'
        self.assertFalse(qualify_pair(rows,self.rows('5'),100000000,900000000)['validated'])


if __name__=='__main__':unittest.main()
