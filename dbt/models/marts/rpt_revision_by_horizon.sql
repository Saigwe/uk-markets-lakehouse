-- How far the headline growth estimate has moved after k more published releases (k = 1, 3, 6, 12, 24),
-- across reference months whose first estimate is in the lakehouse.
with growth as (
    select
        dataset_id, period, vintage,
        case when dataset_id = 'cpih01' then growth_yoy_pct else growth_mom_pct end as growth_pct
    from {{ ref('int_growth_by_vintage') }}
    where ((dataset_id = 'gdp-to-four-decimal-places' and series_code = '{{ var("gdp_headline") }}')
        or (dataset_id = 'cpih01' and series_code = '{{ var("cpih_headline") }}'))
),
numbered as (
    select g.*, row_number() over (partition by dataset_id, period order by vintage) - 1 as releases_after_first
    from growth g
    where growth_pct is not null
),
first as (select dataset_id, period, growth_pct as first_growth_pct from numbered where releases_after_first = 0),
eligible as (
    select f.* from first f
    join {{ ref('rpt_headline_revisions') }} r using (dataset_id, period)
)
select
    n.dataset_id,
    n.releases_after_first                                              as horizon,
    count(*)                                                            as reference_months,
    avg(abs(n.growth_pct - e.first_growth_pct))                         as mean_abs_revision_pp,
    avg(n.growth_pct - e.first_growth_pct)                              as mean_revision_pp,
    avg(case when sign(n.growth_pct) <> sign(e.first_growth_pct) then 1.0 else 0.0 end) as direction_changed_share
from numbered n
join eligible e using (dataset_id, period)
where n.releases_after_first in (1, 3, 6, 12, 24)
group by 1, 2
