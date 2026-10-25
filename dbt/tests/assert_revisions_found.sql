-- Every observation with more than one vintage must appear in the revisions report.
select l.series_id, l.obs_date
from {{ ref('fct_observation_latest') }} l
left join {{ ref('rpt_revisions') }} r on r.series_id = l.series_id and r.obs_date = l.obs_date
where l.vintages > 1 and r.series_id is null
