# Design doc: UK Markets & Macro Lakehouse

| | |
|---|---|
| **Author** | Stanley Igwe |
| **Status** | Core build complete on live ONS and Bank of England data |
| **Last updated** | 2026-10-26 |

## 1. Problem and users
- **Users:** economists and analysts in a finance ministry, central bank or public body; BI teams publishing macro dashboards.
- **Questions they need answered:** What is the latest estimate? What did we know on a given date? How reliable is a first estimate?
- **Current pain (scenario):** a dashboard overwrites each release, so last quarter's briefing can't be reproduced, and a truncated ONS file (like GDP v61's five-series release) silently empties industry charts.

## 2. Requirements
| Type | Requirement |
|---|---|
| Functional | Keep every vintage; publish only audited vintages; answer "as of" questions; measure revisions. |
| Data quality | Block missing headlines, duplicates, lost history and implausible values; record composition changes. |
| Freshness / SLA | Daily at 07:30 UK time, after ONS's 07:00 releases; idempotent, so reruns are free. |
| Scale | ~1M rows today. Iceberg on S3 with Glue and Athena scales to every ONS dataset without changing the code. |
| Cost | Serverless: Fargate minutes, S3 storage, Athena per query with a 10 GB scan cap. |

## 3. Design
- **Layers:** raw files (immutable cache) → Iceberg `macro.observations` (every vintage; published = main) → DuckDB export → dbt silver and gold.
- **Key choices:** one long-format table for all sources, partitioned by dataset; a branch per vintage for write-audit-publish, and a tag per published vintage for time travel; revisions measured on growth computed within each vintage.

## 4. Options considered
| Decision | Options | Chosen | Why |
|---|---|---|---|
| Table format | Parquet files; Delta; Iceberg | Iceberg | Branches and tags give write-audit-publish and time travel natively; Glue and Athena support it on AWS. |
| Vintages | Overwrite; SCD2 rows; keep every release | Keep every release | Revisions and as-of questions need the full history; storage is cheap. |
| Audit failures | Fail the pipeline; drop rows; quarantine the vintage | Quarantine | Readers keep the last good state; the failed vintage stays inspectable; the alert fires once. |
| Revision metric | Index levels; growth rates | Growth rates | Levels change when ONS re-references the index (around v66); growth doesn't. |
| Catalogue | REST; Glue; SQL | SQL locally, Glue on AWS | Same pyiceberg code; local runs need no cloud. |

## 5. Risks and what I'd change at 10x scale
- Quarantined vintages need a human decision: add an approval command that publishes a vintage with a recorded override.
- CPIH zero placeholders are mapped to null by rule; if ONS changes that encoding, the floor audit will flag it.
- At 10x: one Iceberg table per dataset family, snapshot expiry and compaction jobs, Athena views per headline series, and pull concurrency with a rate limiter for the ONS API.
