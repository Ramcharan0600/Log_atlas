# Datasets

Accessibility of the Loghub raw GitHub URLs was verified (HTTP 200) when the loader was implemented:
`https://raw.githubusercontent.com/logpai/loghub/master/<Name>/<Name>_2k.log` and `..._2k.log_structured.csv`.

| Dataset | Lines | Real? | Labels | Used for |
|---|---|---|---|---|
| Linux, Apache, HDFS, OpenSSH, HealthApp (Loghub 2k) | 2,000 each | Real | Template id per line (`EventId`) | template extraction + clustering metrics |
| BGL (Loghub 2k) | 2,000 | Real | Template id + alert/normal flag in the raw line | clustering + anomaly detection |
| Synthetic: application / syslog / nginx | 6k / – / – | **Synthetic** | none | demos, offline use |
| Synthetic: labelled events / anomalies | 6,000 | **Synthetic** | template / normal-anomaly | tests, demos |

Loghub terms: research/academic use — see https://github.com/logpai/loghub. The full-size sets (HDFS_v1 11M lines, BGL 4.7M, Thunderbird 211M) are not bundled; to use one, download it, and upload the raw file (BGL/HDFS formats are parsed natively). Ground truth for those requires the matching label files (not auto-attached).

Dataset selection criteria considered: size, diversity, label availability, format, licence, accessibility, suitability for clustering/anomaly detection. 2k samples were chosen as defaults because they are small, labelled, redistributable for research and fast to run.

Ground-truth attachment is guarded: labels are attached only if raw-record count equals label count. Synthetic data is never substituted silently; it is labelled "Synthetic demo" in the UI, in job records and in reports.

Custom uploads: a `label` column (CSV/JSON/JSONL) holding `normal/anomaly` is treated as anomaly truth; any other values as cluster truth.
