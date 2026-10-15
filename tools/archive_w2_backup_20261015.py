"""Create a portable, byte-preserving evidence snapshot from local W2 records.

No experiment is started and no laboratory host is contacted. Large raw runs,
pcaps, credentials and installed middleware binaries remain outside Git.
"""
import datetime,hashlib,json,re,shutil,sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import url2pathname

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/w2_20261015_resume1'
DEST=ROOT/'reference/w2-20261015'
REPORT=ROOT/'docs/reports/W2_final_20261015.html'

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def compact(value):
    # Preserve all scalars, percentile summaries, qualification and configuration.
    # These long event/sequence arrays remain in the byte-exact results.json.
    if isinstance(value,dict):
        return {k:compact(v) for k,v in value.items() if k not in ['records','missing_requested','missing','received_without_success','received_without_attempt','received_out_of_range','windows','traceback']}
    if isinstance(value,list):return [compact(v) for v in value]
    return value

def main():
    progress=load(BASE/'progress.json');rows=load(BASE/'results.json')
    if progress['state']!='finished_with_skipped_cases' or progress['pending']!=0 or len(rows)!=207:
        raise RuntimeError('Expected completed W2 campaign')
    DEST.mkdir(parents=True,exist_ok=True);REPORT.parent.mkdir(parents=True,exist_ok=True)
    files={name:BASE/name for name in ['results.json','progress.json','restoration.json','matrix.json','source_sha256.json','source_snapshot.tar.gz','runtime_manifest.json','continuation.json','failure_policy.json','capacity_continuity.json','AP_transition_verified.json']}
    files['analysis.json']=BASE/'final_analysis_261015/analysis.json'
    for name,source in files.items():shutil.copyfile(source,DEST/name)
    for row in rows:
        p=DEST/'trials'/row['id']/'summary.json';p.parent.mkdir(parents=True,exist_ok=True)
        obj=compact(row)
        obj['backup_note']='Compact archived summary. Original sequence arrays are in results.json; full raw artifacts remain in local ignored runs/. source_artifacts_root is historical provenance, not a portable path.'
        p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    source_report=ROOT.parent/'html 파일 모음/결과/W2 실험결과/W2 실험 최종 결과 보고서_261015.html'
    body=source_report.read_text(encoding='utf-8')
    row_ids={r['id'] for r in rows}
    def replace_link(match):
        source=Path(url2pathname(urlparse(match.group(1)).path))
        if source.name=='summary.json':
            identifier=re.sub(r'__a\d+$','',source.parent.name)
            if identifier not in row_ids:raise RuntimeError('Unknown report trial '+identifier)
            target='../../reference/w2-20261015/trials/'+identifier+'/summary.json'
        elif source.name in files:target='../../reference/w2-20261015/'+source.name
        else:raise RuntimeError('Unmapped local report link '+str(source))
        return 'href="'+target+'"'
    body=re.sub(r'href="(file:[^"]+)"',replace_link,body)
    body=body.replace('>원자료</a>','>실행 요약</a>')
    banner='<div class="warning"><b>GitHub 백업용 보관본</b>: 링크는 저장소에 포함한 실행 요약과 원본 집계 JSON으로 연결합니다. 전체 pcap·텔레메트리·설치 바이너리·SSH 키는 포함하지 않았으며, 전체 원자료는 연구 PC의 ignored runs/에 유지합니다. 로컬 HTML 원본의 파일 링크만 이 보관본에서 상대 경로로 변환했습니다.</div>'
    body=body.replace('<main>','<main>'+banner,1)
    REPORT.write_text(body,encoding='utf-8',newline='\n')
    (DEST/'README.md').write_text('''# W2 frozen evidence — 2026-10-15

This is **ROSPacer 1.0 (2026-10-15)**, the pre-optimization research backup, not a new experiment. Git tag: `v1.0`; package version: `1.0.0`.

- Ended: 2026-10-15 22:22:32 KST.
- Planned rows: 207. Measured: 198. Blocked scope: 6. Skipped after operational failure: 3.
- T1 E 33 rows retain their original predecessor evidence; corrected F/T3 and P0 use the continuation segment.
- `results.json` and the other campaign JSON files are copied byte-for-byte from the local completed campaign.
- `trials/*/summary.json` are explicitly compact summaries. Large sequence arrays remain in `results.json`; no packet captures or full telemetry are included.
- `source_snapshot.tar.gz` preserves the exact source bytes frozen for the campaign, including original line endings. Current Git source also includes later report generators and backup documentation.
- `source_sha256.json` belongs to that experiment-time snapshot. `MANIFEST.json` hashes this archived evidence set.
- Absolute paths in historical metadata identify the original laboratory files. They are not expected to exist on another machine.
- [Portable final report](../../docs/reports/W2_final_20261015.html).

Limitations: three repeats, one payload size and laboratory radio setup; no Adaptive superiority over Static; T3 latency/rate/fairness exclusions; missing Cyclone buffer-ablation results; incomplete observed delivery in some outage trials. See the report rather than treating every measured row as qualification of every metric.

Verify the archived files without hardware:

```bash
python tools/verify_w2_backup.py
```
''',encoding='utf-8',newline='\n')
    manifest={'snapshot':'ROSPacer 1.0','release_date':'2026-10-15','git_tag':'v1.0','package_version':'1.0.0','created_at':datetime.datetime.now().astimezone().isoformat(),'source_base':BASE.name,'mode':'byte-exact campaign records plus clearly labelled compact per-trial summaries','files':{str(p.relative_to(DEST)).replace('\\','/'):digest(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='MANIFEST.json'},'portable_report':{'path':'../../docs/reports/W2_final_20261015.html','sha256':digest(REPORT)}}
    (DEST/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'evidence_files':len(manifest['files']),'portable_report':str(REPORT),'total_bytes':sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file())},ensure_ascii=True))

if __name__=='__main__':main()
