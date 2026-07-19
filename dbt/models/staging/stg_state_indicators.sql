{{
    config(
        materialized='view',
        tags=['staging', 'fred', 'states']
    )
}}

-- Casts the long state-level Parquet (one row per date+state) into clean
-- typed columns. Year-over-year changes are computed upstream in the
-- transform, per state, on each indicator's native frequency.

with source as (

    select
        cast(date as date) as date,
        cast(state as varchar) as state,
        cast(state_name as varchar) as state_name,

        cast(unemployment_rate as double) as unemployment_rate,
        cast(unemployment_rate_yoy as double) as unemployment_rate_yoy,

        cast(house_price_index as double) as house_price_index,
        cast(house_price_index_yoy_pct as double) as house_price_index_yoy_pct,

        cast(per_capita_income as double) as per_capita_income,
        cast(per_capita_income_yoy_pct as double) as per_capita_income_yoy_pct

    from {{ source('fred_raw', 'state_indicators') }}

)

select *
from source
where date is not null and state is not null
order by state, date
