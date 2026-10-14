-- every complete quarter whose GDP print is negative must be flagged in all
-- three of its months, not only the month the print is dated
select
    date_trunc('quarter', date) as quarter,
    count(*) filter (where flag_gdp_contracting) as flagged_months
from {{ ref('economic_dashboard') }}
group by 1
having bool_or(gdp_mom_pct < 0)
   and count(*) = 3
   and count(*) filter (where flag_gdp_contracting) != 3
