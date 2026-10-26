-- The latest published value of every series and period, with when it first appeared and how many vintages
-- carried it.
select
    dataset_id,
    series_code,
    any_value(series_label)                                             as series_label,
    period,
    arg_max(value, vintage)                                             as value,
    max(vintage)                                                        as latest_vintage,
    min(vintage)                                                        as first_vintage,
    count(*)                                                            as vintages
from {{ ref('stg_lake__observations') }}
group by dataset_id, series_code, period
