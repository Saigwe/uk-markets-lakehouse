-- Every vintage in the warehouse was published through write-audit-publish: it has a tag in the snapshot log.
-- A vintage that failed its audit (GDP v14, v67) must never appear.
select o.dataset_id, o.vintage
from {{ ref('stg_lake__observations') }} o
left join {{ ref('rpt_lake_snapshots') }} s
  on s.dataset_id = o.dataset_id and s.vintage = o.vintage and s.tag is not null
group by 1, 2
having count(s.snapshot_id) = 0
