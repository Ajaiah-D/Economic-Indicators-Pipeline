select date, state, count(*) as n
from {{ ref('state_dashboard') }}
group by date, state
having count(*) > 1
