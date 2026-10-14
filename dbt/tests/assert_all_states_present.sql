-- 50 states + DC; a failed state fetch must not ship silently
select count(distinct state) as n_states
from {{ ref('state_dashboard') }}
having count(distinct state) != 51
