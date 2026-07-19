{{
    config(
        materialized='table',
        tags=['mart', 'dashboard', 'fred', 'vintages']
    )
}}

-- Point-in-time mart: every value each series ever published for every
-- observation date, with first-print and latest-revision window columns so
-- the dashboard can show "as first reported vs as we know it now" without
-- recomputing vintages at page load.

with staged as (

    select * from {{ ref('stg_fred_vintages') }}

),

windowed as (

    select
        *,

        first_value(value) over (
            partition by label, date order by release_date
            rows between unbounded preceding and unbounded following
        ) as first_value,

        first_value(release_date) over (
            partition by label, date order by release_date
            rows between unbounded preceding and unbounded following
        ) as first_release_date,

        last_value(value) over (
            partition by label, date order by release_date
            rows between unbounded preceding and unbounded following
        ) as latest_value,

        count(*) over (partition by label, date) as n_releases

    from staged

)

select
    *,
    current_timestamp as dbt_updated_at
from windowed
order by label, date, release_date
