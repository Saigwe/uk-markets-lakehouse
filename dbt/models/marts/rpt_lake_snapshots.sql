-- The Iceberg snapshot log: every commit to main, the vintage it published and its tag (the time-travel handle).
select
    snapshot_id,
    committed_at,
    dataset_id,
    cast(vintage as bigint)                                             as vintage,
    tag
from {{ source('bronze', 'lake_snapshots') }}
