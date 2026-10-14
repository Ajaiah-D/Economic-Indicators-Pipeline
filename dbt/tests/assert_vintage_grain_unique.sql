select label, date, release_date, count(*) as n
from {{ ref('vintage_dashboard') }}
group by label, date, release_date
having count(*) > 1
