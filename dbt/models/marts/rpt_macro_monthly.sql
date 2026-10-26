-- One row per month: latest GDP growth and its first estimate, CPIH inflation, and Bank of England rates
-- (month-end Bank Rate, monthly average 10-year and 5-year gilt yields from the latest BoE pull).
with gdp as (
    select period as month, latest_growth_pct as gdp_growth_mom_pct, first_growth_pct as gdp_growth_first_estimate_pct
    from {{ ref('rpt_headline_revisions') }} where dataset_id = 'gdp-to-four-decimal-places'
),
gdp_latest as (
    select period as month, growth_mom_pct as gdp_growth_mom_pct_latest
    from {{ ref('int_growth_by_vintage') }}
    where dataset_id = 'gdp-to-four-decimal-places' and series_code = '{{ var("gdp_headline") }}'
    qualify vintage = max(vintage) over ()
),
cpih as (
    select period as month, growth_yoy_pct as cpih_inflation_pct
    from {{ ref('int_growth_by_vintage') }}
    where dataset_id = 'cpih01' and series_code = '{{ var("cpih_headline") }}'
    qualify vintage = max(vintage) over ()
),
latest_pull as (
    select *
    from {{ ref('stg_lake__observations') }}
    where dataset_id = 'iadb-daily-rates'
    qualify vintage = max(vintage) over ()
),
rates as (
    select
        cast(date_trunc('month', period) as date)                       as month,
        arg_max(value, period) filter (where series_code = 'IUDBEDR')   as bank_rate_month_end_pct,
        avg(value) filter (where series_code = 'IUDMNZC')               as gilt_10y_avg_pct,
        avg(value) filter (where series_code = 'IUDSNZC')               as gilt_5y_avg_pct
    from latest_pull
    group by 1
)
select
    coalesce(r.month, l.month, c.month)                                 as month,
    l.gdp_growth_mom_pct_latest,
    g.gdp_growth_first_estimate_pct,
    c.cpih_inflation_pct,
    r.bank_rate_month_end_pct,
    r.gilt_10y_avg_pct,
    r.gilt_5y_avg_pct
from rates r
full join gdp_latest l on l.month = r.month
left join gdp g on g.month = coalesce(r.month, l.month)
left join cpih c on c.month = coalesce(r.month, l.month)
where coalesce(r.month, l.month) >= date '2015-01-01'
