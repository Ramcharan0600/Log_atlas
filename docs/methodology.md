# ML / NLP methodology

**Normalization** replaces variable fields with typed placeholders (UUID, URL, IP[:port], timestamps, hex, paths, ports, measures, `user <ID>`, long numbers, numbers) in a fixed order, preserving words such as *timeout/failed/exception*. Masking (email, phone, token, password, API key, optional IP/identifier) runs first, so no raw secrets are stored.

**Templates**: Drain3 parse tree (depth 4, configurable similarity threshold, default 0.5). Template text is read after the full pass because templates generalise as more lines arrive. Baseline: regex-normalized message as template. Metric: Loghub *grouping accuracy*.

**Features**
- *TF-IDF*: word 1–2-grams (placeholder-aware token pattern) + char_wb 3–5-grams, sublinear TF, L2-normalised, reduced to ≤100 dims with truncated SVD.
- *Embeddings*: `all-MiniLM-L6-v2`, batch 64, normalised, cached on disk by content hash. If the model can't load, an LSA char-n-gram fallback is used and flagged (`lsa-fallback`) in results.

**Clustering** on unique normalized messages. DBSCAN uses frequency sample weights and `eps` from the k-distance knee (clamped 0.05–0.9) unless given. HDBSCAN (`sklearn.cluster.HDBSCAN`) cannot weight points, so `min_cluster_size` shrinks for small unique sets. K-Means baseline uses k = number of Drain templates (≤50) — an informed baseline, not a blind one. Cluster names = title-cased words of the dominant template (fallback: keywords). Related clusters = centroid cosine similarity > 0.3.

**Anomaly detection**: (1) Isolation Forest on 24 feature dims + template rarity + severity + hour-of-day, contamination configurable; (2) rolling z-score over the preceding 12 buckets at 1 min/5 min/1 h for errors, per cluster (5 min) and error ratio (15 min); (3) new pattern (first seen in second half of window), rare templates, component error-rate outliers (z>2). Each anomaly stores a reason. Series longer than 20,000 buckets are skipped (e.g. mixed-year timestamps).

**Priority** (heuristic, not validated): score = 100·Σ wᵢ·fᵢ with severity .35, frequency .15, anomaly .20, trend .10, recency .10, impact (service share) .10. Critical ≥70 (or FATAL and ≥55); High ≥50 or FATAL; Medium ≥30; else Low. The UI shows the factor breakdown.

**Root cause**: for clusters where ≥20% of events are ERROR/FATAL: category from a keyword knowledge base (template first, then representatives), evidence list typed *observed / statistical / model*, preceding clusters starting ≤10 min earlier (temporal order only), evidence strength by counting independent signals (volume ≥20, rising trend, multi-service, each anomaly, predecessor): ≥4 Strong, ≥2 Moderate, else Limited. This is deliberately not a probability.

**Summaries**: rule-based from statistics; optional LLM receives a JSON fact sheet only; output is discarded if it contains numbers absent from the facts.

**Evaluation**: supervised — ARI, NMI, homogeneity, completeness, V-measure (noise points count as singletons, so noise is penalised); unsupervised — silhouette (cosine, non-noise, ≤5,000-point subsample), Davies-Bouldin, Calinski-Harabasz (assume convex clusters and ignore noise: weak for density-based methods). Anomalies — precision/recall/F1 at a threshold equal to the labelled positive rate (like-for-like), ROC-AUC, PR-AUC; baselines: template rarity and severity-only. Runtime via `perf_counter`, memory via `tracemalloc` peak.
