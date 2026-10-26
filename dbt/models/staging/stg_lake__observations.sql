-- One row per dataset, series, period and vintage. Rows written before the BoE source widened the table have no
-- `frequency` (schema evolution); ONS series are monthly.
select
    source,
    dataset_id,
    vintage,
    release_date,
    series_code,
    series_label,
    period,
    value,
    coalesce(frequency, case when source = 'ons' then 'monthly' end) as frequency
from {{ source('bronze', 'observations') }}
