"""Read-only checksum, result-count and portable-link checks; no ROS/hardware."""
import hashlib,json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote,urlparse

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reference/w2-20261015'

def main():
    manifest=json.loads((BASE/'MANIFEST.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files'].items():
        p=(BASE/name).resolve();p.relative_to(BASE.resolve())
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('Checksum mismatch: '+name)
    report=(BASE/manifest['portable_report']['path']).resolve()
    if hashlib.sha256(report.read_bytes()).hexdigest()!=manifest['portable_report']['sha256']:raise ValueError('Report checksum mismatch')
    progress=json.loads((BASE/'progress.json').read_text(encoding='utf-8-sig'))
    assert (progress['finished'],progress['valid_measured'],progress['blocked_scope'],progress['skipped_failed'],progress['pending'])==(207,198,6,3,0)
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            if tag=='a':self.links.extend(v for k,v in attrs if k=='href')
    parser=Links();parser.feed(report.read_text(encoding='utf-8'))
    for url in parser.links:
        parsed=urlparse(url)
        if parsed.scheme=='file':raise ValueError('Nonportable file URL')
        if not parsed.scheme and parsed.path and not (report.parent/unquote(parsed.path)).is_file():raise ValueError('Broken relative report link: '+url)
    print('PASS: '+str(len(manifest['files']))+' evidence checksums, report checksum, 207 result statuses and '+str(len(parser.links))+' portable report links')

if __name__=='__main__':main()
