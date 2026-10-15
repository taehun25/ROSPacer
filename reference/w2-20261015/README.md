# W2 frozen evidence — 2026-10-15

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
