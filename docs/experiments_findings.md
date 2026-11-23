# Findings from the executed experiments

Source: `experiments.md` / `experiments_results.json`, produced by `backend/scripts/run_experiments.py` on six real Loghub 2k samples (single run, fixed seeds, one machine). These are small samples; do not extrapolate to full-scale datasets.

Observations (all read directly from the tables):
- **Drain3 vs regex-only templates**: Drain3 had higher grouping accuracy on Linux (0.685 vs 0.186), Apache (1.000 vs 0.582), OpenSSH (0.718 vs 0.336) and BGL (0.805 vs 0.333); tied on HDFS (0.998). Regex-only is ~30–50× faster but fragments templates. HealthApp grouping accuracy is low for both (0.072 / 0.064) — a limitation we did not resolve.
- **TF-IDF vs embeddings (DBSCAN)**: TF-IDF had the higher ARI on Linux, Apache, HDFS, OpenSSH, BGL and HealthApp (e.g. HDFS 0.999 vs 0.107; Apache 1.000 vs 0.538). Semantic embeddings did **not** beat lexical features here; log messages are template-driven, so exact token overlap is a strong signal. Embeddings were competitive on BGL (0.880 vs 0.911) and OpenSSH (0.855 vs 0.861).
- **DBSCAN vs HDBSCAN**: HDBSCAN (run on unique messages without frequency weights) labelled 16–57% of points (on most sets) as noise on several sets (BGL 0.567) and had lower ARI than DBSCAN almost everywhere (exception: Linux, TF-IDF, 0.902 vs 0.676). DBSCAN with a k-distance eps is therefore the default.
- **K-Means** with k = Drain template count (capped at 50) is a strong baseline on several sets (HDFS 1.000, OpenSSH 0.937, BGL 0.948) but it needs k and cannot flag noise; it received information from Drain, so it is not a blind baseline.
- **Anomaly detection on BGL (alert label)**: Isolation Forest ROC-AUC 0.779, template rarity 0.793, severity-only 0.945 (F1 0.584 vs 0.119). On this sample the alert flag correlates strongly with the logged severity, and the unsupervised content-based detectors were weak. Isolation Forest is not the best detector here.
- **Timings**: embedding feature time in the tables varies (e.g. 53 s on HealthApp when the model first loaded vs ~0.01 s when served from the on-disk cache); compare cluster seconds instead. Synthetic scalability test: 6k → 96k logs at ~9–12k logs/s (evaluation grid disabled).

Caveats: silhouette/Davies-Bouldin/Calinski-Harabasz are unreliable for density-based clusters; single run, no confidence intervals; 2k-line samples.
