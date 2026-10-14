-- monthly series trail by one to two months; 120 days means ingestion has stalled
select max(date) as latest_date
from {{ ref('economic_dashboard') }}
having max(date) < current_date - interval 120 day
