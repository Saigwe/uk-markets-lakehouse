select
    series_id,
    source,
    title,
    unit,
    frequency
from {{ source('bronze', 'series') }}
