-- A GDP print is usable from the row three months after the date FRED stamps
-- on it (Q1 is dated January and published around the end of April). Every
-- complete quarter that opens with a newly usable negative print must be
-- flagged in all three of its months.
with usable as (
    select
        date,
        flag_gdp_contracting,
        lag(gdp_mom_pct, 3) over (order by date) as gdp_print_now_usable
    from {{ ref('economic_dashboard') }}
)

select
    date_trunc('quarter', date) as quarter,
    count(*) filter (where flag_gdp_contracting) as flagged_months
from usable
group by 1
having bool_or(gdp_print_now_usable < 0)
   and count(*) = 3
   and count(*) filter (where flag_gdp_contracting) != 3
