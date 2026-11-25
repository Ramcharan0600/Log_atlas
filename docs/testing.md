# Testing

Backend (`cd backend && python -m pytest`, 50 tests, ~15 s, offline: embeddings disabled via `EMBEDDINGS_ENABLED=false`):
- `tests/test_pipeline.py` — file validation, encodings, multiline, invalid JSONL, CSV/JSON; parsers for every format incl. BGL/HealthApp; missing timestamps, unknown severity, garbage lines; normalization examples from the spec; masking; Drain3 templates and grouping accuracy; TF-IDF/embedding features; DBSCAN/HDBSCAN/K-Means, empty/tiny input, noise handling; anomaly metrics, z-score spikes, flat data (no anomalies); priority, root-cause structure and hedging; LLM fallback; empty files, duplicates, mixed formats.
- `tests/test_api.py` — upload validation and path stripping, 404/422 handling, dataset catalog, full workflow (upload → job → summary → clusters → logs → filters → anomalies → templates → timeline → insights → evaluation → experiment run → JSON/CSV/PDF export → delete), SQL-wildcard safety, secret masking before storage, graceful failures, CSV column mapping (suggestions, validation, saved map, non-CSV rejection).

Frontend: `npm test` (vitest, formatting utilities) and `npx tsc --noEmit` / `npm run build` for type safety. UI flows were not exercised in an automated browser test.

Performance: see the scalability table in `experiments.md` (synthetic, evaluation grid disabled).
