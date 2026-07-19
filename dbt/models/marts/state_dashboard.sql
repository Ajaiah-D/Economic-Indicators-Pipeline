{{
    config(
        materialized='table',
        tags=['mart', 'dashboard', 'fred', 'states']
    )
}}

-- State-level mart: indicators plus each state's rank among the 50 states
-- + DC as of every date. Ranks are computed only across states that have a
-- value on that date, so a late-publishing state can't distort the field.
-- Rank 1 = lowest unemployment / fastest house-price growth / highest income.

with staged as (

    select * from {{ ref('stg_state_indicators') }}

),

ur_ranked as (
    select
        date, state,
        rank() over (partition by date order by unemployment_rate asc) as unemployment_rank
    from staged
    where unemployment_rate is not null
),

hpi_ranked as (
    select
        date, state,
        rank() over (partition by date order by house_price_index_yoy_pct desc) as hpi_growth_rank
    from staged
    where house_price_index_yoy_pct is not null
),

income_ranked as (
    select
        date, state,
        rank() over (partition by date order by per_capita_income desc) as income_rank
    from staged
    where per_capita_income is not null
)

select
    s.*,
    u.unemployment_rank,
    h.hpi_growth_rank,
    i.income_rank,
    current_timestamp as dbt_updated_at

from staged s
left join ur_ranked     u on s.date = u.date and s.state = u.state
left join hpi_ranked    h on s.date = h.date and s.state = h.state
left join income_ranked i on s.date = i.date and s.state = i.state
order by s.state, s.date
