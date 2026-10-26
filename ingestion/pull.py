"""Scheduled pulls into the Iceberg lakehouse, each vintage through write-audit-publish.

    python ingestion/pull.py ons --dataset gdp-to-four-decimal-places --versions all
    python ingestion/pull.py ons --dataset cpih01 --versions last:13
    python ingestion/pull.py boe
    python ingestion/pull.py export --db warehouse/lake.duckdb      # main branch -> DuckDB for dbt

Pulls are incremental and idempotent: a vintage already published (tagged) is skipped, so the schedule can run
as often as it likes. A vintage that failed its audit stays quarantined on its audit branch and is skipped on later
runs until someone passes --retry-quarantined. Exit code 1 only when a NEW vintage fails (that is the alert);
main is never touched by a failed vintage. --offline reads the cached version listing instead of the API.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb  # noqa: E402

import lakehouse  # noqa: E402
import sources  # noqa: E402


def pick(versions: list[dict], spec: str) -> list[dict]:
    if spec == "all":
        return versions
    if spec == "latest":
        return versions[-1:]
    if spec.startswith("last:"):
        return versions[-int(spec.split(":")[1]):]
    lo, hi = (int(x) for x in spec.split("-"))
    return [v for v in versions if lo <= v["version"] <= hi]


def report(dataset: str, vintage: int, result: lakehouse.AuditResult, rows: int) -> None:
    status = "published" if result.passed else "AUDIT FAILED (main unchanged)"
    print(f"{dataset} v{vintage}: {rows:,} rows {status}")
    for name, outcome in result.checks.items():
        if outcome != "ok":
            print(f"    FAIL {name}: {outcome}")
    for name, note in result.warnings.items():
        print(f"    warn {name}: {note}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["ons", "boe", "export"])
    ap.add_argument("--dataset", default="gdp-to-four-decimal-places")
    ap.add_argument("--versions", default="latest", help="all | latest | last:N | A-B")
    ap.add_argument("--warehouse", type=Path, default=Path("warehouse/iceberg"))
    ap.add_argument("--raw", type=Path, default=Path("data/raw"))
    ap.add_argument("--db", default="warehouse/lake.duckdb")
    ap.add_argument("--today", help="override the BoE pull date (YYYY-MM-DD), for reproducible runs")
    ap.add_argument("--offline", action="store_true", help="use the cached ONS version listing (CI, replays)")
    ap.add_argument("--retry-quarantined", action="store_true", help="re-audit vintages that failed before")
    args = ap.parse_args()
    tbl = lakehouse.table(args.warehouse)
    start, failed = time.time(), 0

    if args.command == "ons":
        done = lakehouse.published_vintages(tbl, args.dataset)
        quarantined = set() if args.retry_quarantined else lakehouse.quarantined_vintages(tbl, args.dataset)
        listed = pick(sources.ons_versions(args.dataset, args.raw, offline=args.offline), args.versions)
        todo = [v for v in listed if v["version"] not in done | quarantined]
        if quarantined & {v["version"] for v in listed}:
            print(f"quarantined, awaiting review: {sorted(quarantined & {v['version'] for v in listed})}")
        for v in todo:
            try:
                df = sources.ons_vintage(args.dataset, v, args.raw)
            except Exception as e:  # an upstream gap is reported, not fatal: the next run retries it
                print(f"{args.dataset} v{v['version']}: not downloadable ({type(e).__name__}: {e}); skipped")
                continue
            result = lakehouse.write_audit_publish(tbl, df, args.dataset, v["version"])
            report(args.dataset, v["version"], result, len(df))
            failed += not result.passed
        print(f"{len(todo)} new vintage(s), {len(done)} already published ({time.time() - start:.1f}s)")
    elif args.command == "boe":
        today = dt.date.fromisoformat(args.today) if args.today else None
        df = sources.boe_vintage(args.raw, today=today)
        vintage = int(df.vintage.iat[0])
        if vintage in lakehouse.published_vintages(tbl, "iadb-daily-rates"):
            print(f"iadb-daily-rates v{vintage}: already published")
        else:
            result = lakehouse.write_audit_publish(tbl, df, "iadb-daily-rates", vintage)
            report("iadb-daily-rates", vintage, result, len(df))
            failed += not result.passed
    else:
        arrow = tbl.scan().to_arrow()  # the main branch: published data only
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(args.db)
        con.execute("create schema if not exists bronze")
        con.execute("create or replace table bronze.observations as select * from arrow")
        snaps = [{"snapshot_id": s.snapshot_id, "committed_at": dt.datetime.fromtimestamp(s.timestamp_ms / 1000),
                  "dataset_id": (s.summary.additional_properties or {}).get("dataset_id") if s.summary else None,
                  "vintage": (s.summary.additional_properties or {}).get("vintage") if s.summary else None}
                 for s in tbl.snapshots()]
        tags = {ref.snapshot_id: name for name, ref in tbl.refs().items() if ref.snapshot_ref_type == "tag"}
        import pandas as pd

        log = pd.DataFrame(snaps).assign(tag=lambda d: d.snapshot_id.map(tags))
        con.execute("create or replace table bronze.lake_snapshots as select * from log")
        print(f"exported {arrow.num_rows:,} published rows and {len(log)} snapshots to {args.db}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
