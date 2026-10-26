"""The Iceberg lakehouse: one long-format `macro.observations` table holding every vintage of every series.

Write-audit-publish, per vintage:
  1. WRITE   append the vintage to a branch `audit-<dataset>-v<vintage>` cut from main; readers on main see nothing
  2. AUDIT   read the branch back and run the audits below against it and the previous published vintage
  3. PUBLISH fast-forward main to the branch head, tag it `<dataset>-v<vintage>`, drop the branch
A failed audit leaves main untouched and keeps the branch for inspection.

Schema evolution: a frame with columns the table lacks (the BoE pull adds `frequency`) widens the table with
union_by_name; earlier snapshots keep their old schema, and time travel shows it.

Catalogue: a SQL catalogue (SQLite file) over a local warehouse directory. In the cloud the same code uses the
Glue catalogue and S3 (terraform/), switched by LAKEHOUSE_CATALOG=glue.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow as pa
from pyiceberg.expressions import And, EqualTo
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import DateType, DoubleType, LongType, NestedField, StringType

NAMESPACE, TABLE = "macro", "observations"
SCHEMA = Schema(
    NestedField(1, "source", StringType(), required=False),
    NestedField(2, "dataset_id", StringType(), required=False),
    NestedField(3, "vintage", LongType(), required=False),
    NestedField(4, "release_date", DateType(), required=False),
    NestedField(5, "series_code", StringType(), required=False),
    NestedField(6, "series_label", StringType(), required=False),
    NestedField(7, "period", DateType(), required=False),
    NestedField(8, "value", DoubleType(), required=False),
)
SPEC = PartitionSpec(PartitionField(source_id=2, field_id=1000, transform=IdentityTransform(), name="dataset_id"))

# Plausibility bounds per dataset, set by real extremes rather than guesses:
#  - every value must be positive (index floor 1: accommodation and food fell to ~10 in April 2020)
#  - only the HEADLINE has an upper level bound: industries legitimately sit far from 100 (mining was above 300
#    in 1997 after ONS re-referenced the index; CPIH data-processing equipment was 5,269 in 1988, 2015 = 100)
#  - headline month-on-month moves within 30% (GDP fell about 20% in April 2020)
BOUNDS = {
    "gdp-to-four-decimal-places": {"min": 1, "headline_max": 200, "max_abs_change": 0.30, "headline": "A--T"},
    "cpih01": {"min": 1, "headline_max": 300, "max_abs_change": 0.10, "headline": "CP00"},
    "iadb-daily-rates": {"min": -2, "headline_max": 20, "max_abs_change": None, "headline": "IUDBEDR"},
}


def catalog(warehouse: Path):
    if os.environ.get("LAKEHOUSE_CATALOG") == "glue":
        from pyiceberg.catalog.glue import GlueCatalog

        return GlueCatalog("lake", **{"warehouse": os.environ["LAKEHOUSE_WAREHOUSE"]})
    from pyiceberg.catalog.sql import SqlCatalog

    warehouse.mkdir(parents=True, exist_ok=True)
    # a plain path, not a file:// URI: pyiceberg on Windows mangles file URIs
    return SqlCatalog("lake", uri=f"sqlite:///{(warehouse / 'catalog.db').as_posix()}", warehouse=str(warehouse.resolve()))


def table(warehouse: Path):
    cat = catalog(warehouse)
    cat.create_namespace_if_not_exists(NAMESPACE)
    if not cat.table_exists(f"{NAMESPACE}.{TABLE}"):
        tbl = cat.create_table(f"{NAMESPACE}.{TABLE}", schema=SCHEMA, partition_spec=SPEC,
                               properties={"format-version": "2", "write.wap.enabled": "true"})
        # an empty first snapshot on main, so every real write can go to a branch cut from it
        tbl.append(SCHEMA.as_arrow().empty_table(), snapshot_properties={"genesis": "true"})
    return cat.load_table(f"{NAMESPACE}.{TABLE}")


def published_vintages(tbl, dataset: str) -> set[int]:
    return {int(name.rsplit("-v", 1)[1]) for name, ref in tbl.refs().items()
            if ref.snapshot_ref_type == "tag" and name.startswith(f"{dataset}-v")}


def quarantined_vintages(tbl, dataset: str) -> set[int]:
    """Vintages whose audit failed: their audit branch is kept for inspection."""
    prefix = f"audit-{dataset}-v"
    return {int(name[len(prefix):]) for name in tbl.refs() if name.startswith(prefix)}


@dataclass
class AuditResult:
    passed: bool
    checks: dict[str, str] = field(default_factory=dict)    # blocking: any failure keeps the vintage off main
    warnings: dict[str, str] = field(default_factory=dict)  # recorded, not blocking


def audit(new: pd.DataFrame, previous: pd.DataFrame | None, dataset: str) -> AuditResult:
    """Block what would break readers; warn about what only changes the shape of the release."""
    b, checks, warnings = BOUNDS[dataset], {}, {}
    head = new[new.series_code == b["headline"]]
    checks["not empty"] = "ok" if len(new) else "no rows"
    checks["headline series present"] = "ok" if len(head) else f"{b['headline']} missing"
    checks["no null keys"] = "ok" if not new[["series_code", "period"]].isna().any().any() else "null series_code or period"
    dupes = int(new.duplicated(["series_code", "period"]).sum())
    checks["one value per series and period"] = "ok" if dupes == 0 else f"{dupes} duplicates"
    below = int((new.value.dropna() < b["min"]).sum())
    checks[f"all values at least {b['min']}"] = "ok" if below == 0 else f"{below} below the floor"
    above = int((head.value > b["headline_max"]).sum())
    checks[f"headline at most {b['headline_max']}"] = "ok" if above == 0 else f"{above} above"
    if b["max_abs_change"]:
        jumps = int((head.sort_values("period").value.pct_change().abs() > b["max_abs_change"]).sum())
        checks[f"headline month-on-month moves within {b['max_abs_change']:.0%}"] = "ok" if jumps == 0 else f"{jumps} implausible jumps"
    malformed, raw = new.attrs.get("malformed_rows", 0), new.attrs.get("raw_rows", len(new))
    checks["malformed rows under 1%"] = "ok" if malformed <= 0.01 * raw else f"{malformed} of {raw}"
    if malformed:
        warnings["malformed rows dropped"] = str(malformed)
    if previous is not None and len(previous):
        prev_head = previous[previous.series_code == b["headline"]]
        lost = set(prev_head.period) - set(head.period)
        checks["headline history not lost"] = "ok" if not lost else f"{len(lost)} months missing"
        added, dropped = set(new.series_code) - set(previous.series_code), set(previous.series_code) - set(new.series_code)
        if added or dropped:
            warnings["series composition changed"] = f"+{len(added)} / -{len(dropped)} series"
    return AuditResult(all(v == "ok" for v in checks.values()), checks, warnings)


def _conform(tbl, df: pd.DataFrame) -> pa.Table:
    """Widen the table for new columns (schema evolution), then shape the frame to the table's schema."""
    arrow = pa.Table.from_pandas(df, preserve_index=False)
    new_cols = set(arrow.schema.names) - {f.name for f in tbl.schema().fields}
    if new_cols:
        with tbl.update_schema() as update:
            update.union_by_name(arrow.schema)
        tbl.refresh()
    target = tbl.schema().as_arrow()
    columns = [arrow[f.name].cast(f.type) if f.name in arrow.schema.names else pa.nulls(len(arrow), f.type)
               for f in target]
    return pa.Table.from_arrays(columns, schema=target)


def write_audit_publish(tbl, df: pd.DataFrame, dataset: str, vintage: int) -> AuditResult:
    branch = f"audit-{dataset}-v{vintage}"
    attrs = dict(df.attrs)
    data = _conform(tbl, df)
    head = tbl.current_snapshot()
    if branch in tbl.refs():  # a retry replaces the branch left by an earlier failed audit
        tbl.manage_snapshots().remove_branch(branch).commit()
    tbl.manage_snapshots().create_branch(head.snapshot_id, branch).commit()
    tbl.append(data, branch=branch, snapshot_properties={"dataset_id": dataset, "vintage": str(vintage)})
    tbl.refresh()

    staged = tbl.snapshot_by_name(branch)
    rows = EqualTo("dataset_id", dataset)
    new = tbl.scan(snapshot_id=staged.snapshot_id, row_filter=And(rows, EqualTo("vintage", vintage))).to_pandas()
    new.attrs.update(attrs)
    earlier = [v for v in published_vintages(tbl, dataset) if v < vintage]
    previous = None
    if earlier:
        previous = tbl.scan(snapshot_id=head.snapshot_id,
                            row_filter=And(rows, EqualTo("vintage", max(earlier)))).to_pandas()
    result = audit(new, previous, dataset)
    if not result.passed:
        return result  # main untouched; the branch stays for inspection
    with tbl.manage_snapshots() as ms:
        ms.set_current_snapshot(snapshot_id=staged.snapshot_id)  # fast-forward main
        ms.create_tag(staged.snapshot_id, f"{dataset}-v{vintage}")
        ms.remove_branch(branch)
    tbl.refresh()
    return result
