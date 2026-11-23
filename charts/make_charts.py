"""README charts from the gold marts. Usage: python charts/make_charts.py [--db warehouse/lake.duckdb] [--out docs/charts]"""
import argparse
from datetime import date
from pathlib import Path

import duckdb
import matplotlib.dates as mdates

import style as st

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--db", default=str(ROOT / "warehouse" / "lake.duckdb"))
ap.add_argument("--out", default=str(ROOT / "docs" / "charts"))
a = ap.parse_args()
OUT = Path(a.out)
con = duckdb.connect(a.db, read_only=True)

# 1. GDP monthly growth: what was first published vs what the latest vintage says
g = con.execute("""select period, first_growth_pct::double, latest_growth_pct::double from gold.rpt_headline_revisions
                   where dataset_id = 'gdp-to-four-decimal-places' and first_growth_pct is not null order by period""").fetchall()
h = con.execute("""select horizon, mean_abs_revision_pp::double from gold.rpt_revision_by_horizon
                   where dataset_id = 'gdp-to-four-decimal-places' order by horizon""").fetchall()
x = [r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])[:7] + "-01") for r in g]
f, ax = st.fig(8, 3.4)
ax.plot(x, [r[1] for r in g], color=st.MUTED, lw=1.6, marker="o", ms=3, label="First estimate")
ax.plot(x, [r[2] for r in g], color=st.S[0], lw=2, label="Latest vintage")
ax.axhline(0, color=st.TEXT2, lw=0.8)
ys = [v for r in g for v in r[1:] if v is not None]
ax.set_ylim(min(ys) - 0.4, max(ys) + 0.4)
ax.yaxis.set_major_formatter(st.FuncFormatter(lambda v, _: f"{v:+.1f}%"))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
sub = "UK monthly GDP growth for each month, as first published and as it stands now (every vintage kept in Iceberg)"
if h:
    last = h[-1]
    title = f"{last[0]} releases on, a month's GDP growth has moved {last[1]:.2f} pp on average"
else:
    title = "Monthly GDP growth, first estimate vs latest"
st.head(ax, title, sub, legend=True)
st.save(f, OUT / "gdp_revisions.png")

# 2. Inflation, Bank Rate and the 10-year gilt
m = con.execute("""select month, cpih_inflation_pct::double, bank_rate_month_end_pct::double, gilt_10y_avg_pct::double
                   from gold.rpt_macro_monthly where month >= date '2015-01-01' order by month""").fetchall()
f, ax = st.fig(8, 3.4)
for i, (lab, col) in enumerate([("CPIH inflation, year on year", st.S[1]), ("Bank Rate, month end", st.S[0]),
                                ("10-year gilt yield, monthly average", st.S[2])]):
    pts = [(r[0], r[1 + i]) for r in m if r[1 + i] is not None]
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=2, label=lab)
ax.yaxis.set_major_formatter(st.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.set_ylim(bottom=0)
st.head(ax, "Inflation, policy rate and gilt yields from one lakehouse",
        "ONS CPIH and Bank of England series joined by month in rpt_macro_monthly", legend=True, ncol=3)
st.save(f, OUT / "macro_monthly.png")
print(f"wrote charts to {OUT}")
