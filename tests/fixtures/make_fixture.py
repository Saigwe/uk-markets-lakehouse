"""Synthetic raw files in the exact ONS and Bank of England formats, plus the ONS version listing, so CI runs the
real pull (offline), write-audit-publish, export and dbt without touching the live APIs.

GDP: 8 vintages of 3 series. Each vintage adds a month and revises the last three; vintage 5 re-references the
index (every level halves, growth unchanged) to prove revisions are measured on growth. CPIH: 4 unrevised vintages.

Usage: python tests/fixtures/make_fixture.py --raw data/fixture/raw
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

GDP_SERIES = {"A--T": "A-T : Monthly GDP", "B--E": "B-E : Production Industries", "G--T": "G-T : Services"}
CPIH_SERIES = {"CP00": "Overall Index", "CP01": "01 Food and non-alcoholic beverages"}


def ons_csv(path: Path, rows: list[tuple], code_col: str, label_col: str, value_col: str = "v4_0") -> None:
    df = pd.DataFrame(rows, columns=[value_col, "mmm-yy", "code", "label"])
    df.insert(2, "Time", df["mmm-yy"])
    df.insert(3, "uk-only", "K02000001")
    df.insert(4, "Geography", "United Kingdom")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.rename(columns={"code": code_col, "label": label_col}).to_csv(path, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=Path("data/fixture/raw"))
    args = ap.parse_args()
    rng = np.random.default_rng(16)
    months = pd.period_range("2019-01", "2024-12", freq="M")
    truth = {s: 100 * np.cumprod(1 + rng.normal(0.002, 0.006, len(months))) for s in GDP_SERIES}

    listing = []
    for v in range(1, 9):
        n = len(months) - 8 + v  # each release adds a month
        rows = []
        for s, label in GDP_SERIES.items():
            level = truth[s][:n].copy()
            level[-3:] *= 1 + rng.normal(0, 0.002, 3)  # the latest months are provisional
            if v >= 5:
                level *= 0.5  # re-referenced index
            rows += [(round(x, 4), m.strftime("%b-%y"), s, label) for x, m in zip(level, months[:n])]
        value_col = "V4_0" if v % 2 else "v4_0"  # the real files mix both spellings
        ons_csv(args.raw / "ons" / "gdp-to-four-decimal-places" / f"v{v}.csv", rows,
                "sic-unofficial", "UnofficialStandardIndustrialClassification", value_col)
        listing.append({"version": v, "release_date": str((months[n - 1] + 2).to_timestamp().date()), "csv_url": "fixture"})
    (args.raw / "ons" / "gdp-to-four-decimal-places" / "versions.json").write_text(json.dumps(listing, indent=1))

    listing = []
    cpih = {s: 100 * np.cumprod(1 + rng.normal(0.003, 0.002, len(months))) for s in CPIH_SERIES}
    for v in range(1, 5):
        n = len(months) - 4 + v
        rows = [(round(x, 1), m.strftime("%b-%y"), s, label)
                for s, label in CPIH_SERIES.items() for x, m in zip(cpih[s][:n], months[:n])]
        ons_csv(args.raw / "ons" / "cpih01" / f"v{v}.csv", rows, "cpih1dim1aggid", "Aggregate")
        listing.append({"version": v, "release_date": str((months[n - 1] + 1).to_timestamp().date()), "csv_url": "fixture"})
    (args.raw / "ons" / "cpih01" / "versions.json").write_text(json.dumps(listing, indent=1))

    days = pd.bdate_range("2019-01-02", "2024-12-31")
    boe = pd.DataFrame({"DATE": days.strftime("%d %b %Y"),
                        "IUDBEDR": np.repeat([0.75, 0.1, 1.25, 4.5, 5.25], len(days) // 5 + 1)[:len(days)],
                        "IUDMNZC": np.round(1.5 + np.cumsum(rng.normal(0, 0.03, len(days))), 4),
                        "IUDSNZC": np.round(1.0 + np.cumsum(rng.normal(0, 0.03, len(days))), 4)})
    (args.raw / "boe").mkdir(parents=True, exist_ok=True)
    boe.to_csv(args.raw / "boe" / "iadb_20250101.csv", index=False)
    print(f"wrote fixture ONS (GDP 8 vintages, CPIH 4) and BoE files to {args.raw}")


if __name__ == "__main__":
    main()
