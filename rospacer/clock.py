"""Qualify relative clocks from retained chrony samples on a direct wire."""
import math
import re


def qualify_pair(source, reference, start_wall_ns, end_wall_ns):
    report={'validated':False,'target_ms':.2,'exclusion_ms':1.,
            'scope':'relative laptop4-to-laptop5 time; not UTC accuracy',
            'method':'abs(system correction) + root delay/2 + root dispersion',
            'errors':[]}
    if not source or not reference or end_wall_ns<=start_wall_ns:
        report['errors'].append('missing clock samples or measurement span')
        return report
    maxima=[]
    for label,rows in [('4',source),('5',reference)]:
        times=[r['wall_ns'] for r in rows]
        if min(times)>start_wall_ns or max(times)<end_wall_ns:
            report['errors'].append(label+': samples do not cover measurement')
        if any(b<=a or b-a>2e9 for a,b in zip(times,times[1:])):
            report['errors'].append(label+': clock discontinuity or sampling gap')
        relevant=[r for r in rows if start_wall_ns-1e9<=r['wall_ns']<=end_wall_ns+1e9]
        bounds=[]
        for r in relevant:
            t=r['tracking']['stdout']
            try:
                vals=[float(re.search(k+r'\s*:\s*([+-]?[0-9.]+)',t)[1]) for k in ['System time','Root delay','Root dispersion']]
                bound=1000*(abs(vals[0])+vals[1]/2+vals[2])
                if not math.isfinite(bound) or min(vals[1:])<0 or 'Leap status     : Normal' not in t:
                    raise ValueError('invalid tracking')
                if label=='4':
                    if not re.search(r'^\^\*\s+192\.168\.50\.1\s',r['sources']['stdout'],re.M):
                        raise ValueError('wired reference not selected')
                    ntp=r['ntpdata']['stdout']
                    if not re.search(r'Remote address\s*: 192\.168\.50\.1.*?Local address\s*: 192\.168\.50\.2',ntp,re.S):
                        raise ValueError('wired NTP path absent')
                elif 'Reference ID    : 7F7F0101' not in t:
                    raise ValueError('reference clock changed')
                bounds.append(bound)
            except (TypeError,ValueError,AttributeError):
                report['errors'].append(label+': invalid clock evidence')
        maxima.append(max(bounds,default=float('inf')))
    report['relative_error_bound_ms']=sum(maxima)
    report['target_met']=report['relative_error_bound_ms']<=.2
    report['validated']=not report['errors'] and report['relative_error_bound_ms']<=1.
    report['errors']=sorted(set(report['errors']))
    return report
