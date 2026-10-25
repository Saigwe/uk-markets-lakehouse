select
    series_id,
    cast(obs_date as date)             as obs_date,
    value,
    vintage_ts
from {{ source('bronze', 'observations') }}
