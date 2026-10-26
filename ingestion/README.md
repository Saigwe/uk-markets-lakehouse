# Ingestion

| File | Role |
|---|---|
| `sources.py` | Fetch and normalise ONS dataset versions and Bank of England IADB series; cache raw files under `data/raw`; save each ONS version listing to `versions.json`. Polite pacing and backoff on HTTP 429. |
| `lakehouse.py` | The Iceberg table, schema evolution, the audits, and write-audit-publish (branch, audit, fast-forward main, tag). |
| `pull.py` | CLI: `ons`, `boe`, `export`. Incremental and idempotent; quarantined vintages are skipped until `--retry-quarantined`. |

```bash
python ingestion/pull.py ons --dataset gdp-to-four-decimal-places --versions all
python ingestion/pull.py ons --dataset cpih01 --versions last:13
python ingestion/pull.py boe
python ingestion/pull.py export --db warehouse/lake.duckdb
```
