"""Fetch and normalise the two public sources. Raw downloads are cached under data/raw (the immutable landing
zone): a file that is already there is never fetched again, so re-runs are cheap and reproducible.

ONS (api.beta.ons.gov.uk): every release of a dataset is a numbered version with its own CSV, so pulling all
versions gives the real vintage history.
    gdp-to-four-decimal-places   monthly GDP index by industry (headline = A--T)
    cpih01                       CPIH index by COICOP aggregate (headline = CP00)
Bank of England database (IADB): daily series, pulled whole each time; the pull date is the vintage.
    IUDBEDR Bank Rate · IUDMNZC 10-year gilt nominal zero-coupon yield · IUDSNZC 5-year
"""
from __future__ import annotations

import datetime as dt
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

USER_AGENT = "uk-markets-lakehouse/1.0 (+https://github.com/Saigwe/uk-markets-lakehouse)"
ONS_API = "https://api.beta.ons.gov.uk/v1/datasets"
BOE_IADB = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
            "&Datefrom=01/Jan/{start}&Dateto=now&SeriesCodes={codes}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
BOE_SERIES = {"IUDBEDR": "Bank Rate", "IUDMNZC": "10-year gilt nominal zero-coupon yield",
              "IUDSNZC": "5-year gilt nominal zero-coupon yield"}
DIMENSION_COLUMNS = {"gdp-to-four-decimal-places": ("sic-unofficial", "UnofficialStandardIndustrialClassification"),
                     "cpih01": ("cpih1dim1aggid", "Aggregate")}


def _get(url: str, retries: int = 6) -> bytes:
    """GET with polite pacing; on 429 or a transient error, wait (Retry-After if given) and try again."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            time.sleep(1.0)  # be a good citizen of a free public API
            return body
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == retries - 1:
                raise
            wait = float(e.headers.get("Retry-After") or 5 * 2 ** attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            wait = 5 * 2 ** attempt
        time.sleep(min(wait, 120))


def ons_versions(dataset: str, raw: Path, offline: bool = False) -> list[dict]:
    """All published versions of a dataset's time-series edition: [{version, release_date, csv_url}].
    The listing is saved to raw/ons/<dataset>/versions.json (provenance, and what --offline reads)."""
    manifest = raw / "ons" / dataset / "versions.json"
    if offline:
        return json.loads(manifest.read_text())
    out, offset = [], 0
    while True:
        page = json.loads(_get(f"{ONS_API}/{dataset}/editions/time-series/versions?limit=100&offset={offset}"))
        # a few published versions list no downloads (e.g. GDP v56): try the standard download path instead
        out += [{"version": int(v["version"]), "release_date": v["release_date"][:10],
                 "csv_url": v.get("downloads", {}).get("csv", {}).get("href")
                 or f"https://download.ons.gov.uk/downloads/datasets/{dataset}/editions/time-series/versions/{v['version']}.csv"}
                for v in page["items"]]
        offset += page["count"]
        if offset >= page["total_count"]:
            out = sorted(out, key=lambda v: v["version"])
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps(out, indent=1))
            return out


def ons_vintage(dataset: str, version: dict, raw: Path) -> pd.DataFrame:
    path = raw / "ons" / dataset / f"v{version['version']}.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(version["csv_url"]))
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.lower() for c in df.columns]  # releases mix "V4_0" and "v4_0"
    code, label = (c.lower() for c in DIMENSION_COLUMNS[dataset])
    value = next(c for c in df.columns if c.startswith("v4_"))
    values = pd.to_numeric(df[value].replace("", None), errors="coerce")
    if dataset == "cpih01":
        # CPIH files fill months before a component existed (1988-2000) with 0.0; a zero price index is impossible,
        # so these are missing values, not observations
        values = values.mask(values == 0)
    period = pd.to_datetime(df["mmm-yy"], format="%b-%y", errors="coerce")
    # some releases (GDP v6, v7) contain garbled rows such as "Se.- T" with no value: drop and count them
    malformed = period.isna() & values.isna()
    out = pd.DataFrame({
        "source": "ons", "dataset_id": dataset, "vintage": version["version"],
        "release_date": pd.to_datetime(version["release_date"]).date(),
        "series_code": df[code], "series_label": df[label],
        "period": period.dt.date, "value": values,
    })[~malformed].reset_index(drop=True)
    out.attrs["malformed_rows"] = int(malformed.sum())
    out.attrs["raw_rows"] = len(df)
    return out


def boe_vintage(raw: Path, start_year: int = 2015, today: dt.date | None = None) -> pd.DataFrame:
    today = today or dt.date.today()
    path = raw / "boe" / f"iadb_{today:%Y%m%d}.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(BOE_IADB.format(start=start_year, codes=",".join(BOE_SERIES))))
    wide = pd.read_csv(io.BytesIO(path.read_bytes()))
    long = wide.melt(id_vars="DATE", var_name="series_code", value_name="value").dropna(subset=["value"])
    return pd.DataFrame({
        "source": "boe", "dataset_id": "iadb-daily-rates", "vintage": int(f"{today:%Y%m%d}"),
        "release_date": today, "series_code": long.series_code, "series_label": long.series_code.map(BOE_SERIES),
        "period": pd.to_datetime(long.DATE, format="%d %b %Y").dt.date,
        "value": pd.to_numeric(long.value, errors="coerce"), "frequency": "daily",
    })
