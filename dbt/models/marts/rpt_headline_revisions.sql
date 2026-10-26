-- First estimate vs latest estimate of the headline growth rate, per reference month:
--   GDP:  month-on-month growth of total GDP (A--T)
--   CPIH: 12-month inflation rate of all items (CP00)
-- Only months whose first estimate is in the lakehouse (first published after the earliest vintage loaded) count,
-- otherwise "first" would just mean "oldest release we have".
with growth as (
    select
        dataset_id, period, vintage, release_date,
        case when dataset_id = 'cpih01' then growth_yoy_pct else growth_mom_pct end as growth_pct
    from {{ ref('int_growth_by_vintage') }}
    where (dataset_id = 'gdp-to-four-decimal-places' and series_code = '{{ var("gdp_headline") }}')
       or (dataset_id = 'cpih01' and series_code = '{{ var("cpih_headline") }}')
),
loaded as (select dataset_id, min(vintage) as first_loaded from growth group by 1),
ranked as (
    select
        g.*,
        row_number() over (partition by g.dataset_id, g.period order by g.vintage)      as estimate_number,
        count(*) over (partition by g.dataset_id, g.period)                            as estimates
    from growth g
    where g.growth_pct is not null
)
select
    r.dataset_id,
    r.period,
    min(r.vintage)                                                      as first_vintage,
    min(r.release_date)                                                 as first_release_date,
    max(r.vintage)                                                      as latest_vintage,
    any_value(r.estimates)                                              as estimates,
    arg_min(r.growth_pct, r.vintage)                                    as first_growth_pct,
    arg_max(r.growth_pct, r.vintage)                                    as latest_growth_pct,
    arg_max(r.growth_pct, r.vintage) - arg_min(r.growth_pct, r.vintage) as revision_pp,
    sign(arg_max(r.growth_pct, r.vintage)) <> sign(arg_min(r.growth_pct, r.vintage)) as direction_changed
from ranked r
join loaded l using (dataset_id)
group by r.dataset_id, r.period, l.first_loaded
having min(r.vintage) > l.first_loaded
