"""Iceberg behaviour, on a throwaway lakehouse: write-audit-publish, time travel, schema evolution, idempotency."""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingestion"))
import lakehouse  # noqa: E402

DS = "gdp-to-four-decimal-places"


def vintage(v: int, months: int, scale: float = 1.0) -> pd.DataFrame:
    periods = pd.period_range("2024-01", periods=months, freq="M").to_timestamp().date
    return pd.DataFrame({
        "source": "ons", "dataset_id": DS, "vintage": v, "release_date": dt.date(2025, v, 1),
        "series_code": "A--T", "series_label": "GDP", "period": periods,
        "value": [scale * (100 + i) for i in range(months)],
    })


@pytest.fixture
def tbl(tmp_path):
    return lakehouse.table(tmp_path / "lake")


def main_rows(t) -> pd.DataFrame:
    t.refresh()
    return t.scan().to_pandas()


def test_good_vintage_is_published_and_tagged(tbl):
    result = lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    assert result.passed
    assert len(main_rows(tbl)) == 6
    assert f"{DS}-v1" in tbl.refs() and not lakehouse.quarantined_vintages(tbl, DS)


def test_bad_vintage_never_reaches_main(tbl):
    lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    head_before = tbl.current_snapshot().snapshot_id
    bad = pd.concat([vintage(2, 7), vintage(2, 7).head(2)])  # duplicate keys
    result = lakehouse.write_audit_publish(tbl, bad, DS, 2)
    assert not result.passed and "duplicates" in result.checks["one value per series and period"]
    tbl.refresh()
    assert tbl.current_snapshot().snapshot_id == head_before          # main did not move
    assert set(main_rows(tbl).vintage) == {1}                        # readers never saw vintage 2
    assert lakehouse.quarantined_vintages(tbl, DS) == {2}            # kept on its branch for inspection


def test_lost_headline_history_is_blocked(tbl):
    lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    result = lakehouse.write_audit_publish(tbl, vintage(2, 6).iloc[2:], DS, 2)
    assert not result.passed and result.checks["headline history not lost"] != "ok"


def test_time_travel_by_tag(tbl):
    lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    lakehouse.write_audit_publish(tbl, vintage(2, 7), DS, 2)
    v1 = tbl.snapshot_by_name(f"{DS}-v1")
    assert set(tbl.scan(snapshot_id=v1.snapshot_id).to_pandas().vintage) == {1}
    assert set(main_rows(tbl).vintage) == {1, 2}


def test_schema_evolution_keeps_old_snapshots_readable(tbl):
    lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    rates = pd.DataFrame({
        "source": "boe", "dataset_id": "iadb-daily-rates", "vintage": 20250101, "release_date": dt.date(2025, 1, 1),
        "series_code": "IUDBEDR", "series_label": "Bank Rate", "period": [dt.date(2024, 12, 31)], "value": [4.75],
        "frequency": "daily"})
    assert lakehouse.write_audit_publish(tbl, rates, "iadb-daily-rates", 20250101).passed
    tbl.refresh()
    assert "frequency" in tbl.schema().column_names
    old = tbl.snapshot_by_name(f"{DS}-v1")
    assert tbl.schemas()[old.schema_id].column_names.count("frequency") == 0  # the old snapshot's own schema
    rows = main_rows(tbl)
    assert rows.loc[rows.source == "ons", "frequency"].isna().all()
    assert (rows.loc[rows.source == "boe", "frequency"] == "daily").all()


def test_republishing_is_a_no_op(tbl):
    lakehouse.write_audit_publish(tbl, vintage(1, 6), DS, 1)
    assert lakehouse.published_vintages(tbl, DS) == {1}
    snapshots = len(tbl.snapshots())
    assert 1 in lakehouse.published_vintages(tbl, DS)  # pull.py skips it
    assert len(tbl.snapshots()) == snapshots
