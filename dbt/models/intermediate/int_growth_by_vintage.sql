-- Growth computed INSIDE each vintage: month-on-month for GDP, 12-month for CPIH (the headline inflation rate).
-- Comparing growth rather than index levels makes revisions immune to ONS re-referencing the index (GDP's base
-- year changed around v66, which moves every level but not the growth). A lag only counts when it is exactly the
-- month (or year) before, so a gap in a release never produces a fake growth rate.
with monthly as (
    select *
    from {{ ref('stg_lake__observations') }}
    where frequency = 'monthly'
),
lagged as (
    select
        m.*,
        lag(value) over w                                               as prev_value,
        lag(period) over w                                              as prev_period,
        lag(value, 12) over w                                           as year_ago_value,
        lag(period, 12) over w                                          as year_ago_period
    from monthly m
    window w as (partition by dataset_id, series_code, vintage order by period)
)
select
    dataset_id,
    series_code,
    series_label,
    period,
    vintage,
    release_date,
    value,
    -- rounded to 1e-6 percentage points: far below any published precision, and it keeps comparisons exact
    case when prev_period = period - interval 1 month then round(100.0 * (value / prev_value - 1), 6) end as growth_mom_pct,
    case when year_ago_period = period - interval 12 month then round(100.0 * (value / year_ago_value - 1), 6) end as growth_yoy_pct
from lagged
