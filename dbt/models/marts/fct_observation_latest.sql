-- Latest vintage of each observation, plus how many vintages exist.
select
    series_id,
    obs_date,
    value,
    vintage_ts,
    count(*) over (partition by series_id, obs_date) as vintages
from {{ ref('stg_bronze__observations') }}
qualify row_number() over (partition by series_id, obs_date order by vintage_ts desc) = 1
