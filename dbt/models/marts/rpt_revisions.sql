-- First estimate vs latest value for observations that were revised.
select
    series_id,
    obs_date,
    first(value order by vintage_ts)                                    as first_value,
    last(value order by vintage_ts)                                     as latest_value,
    last(value order by vintage_ts) - first(value order by vintage_ts)  as revision
from {{ ref('stg_bronze__observations') }}
group by 1, 2
having count(*) > 1
