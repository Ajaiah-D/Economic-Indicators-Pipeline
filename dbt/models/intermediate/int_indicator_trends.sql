{{
    config(
        materialized='view',
        tags=['intermediate', 'fred']
    )
}}

-- Adds six binary stress flags and a composite signal score.
-- recession_watch fires when 3+ flags are active simultaneously,
-- which historically lines up with the lead-up to 2008 and 2020.

with staged as (

    select * from {{ ref('stg_fred_indicators') }}

),

lagged as (

    select
        *,
        lag(unemployment_rate_3m_avg, 3) over (order by date) as unemployment_3m_avg_lag3

    from staged

),

flagged as (

    select
        date,

        cpi,
        unemployment_rate,
        gdp,
        fed_funds_rate,
        housing_starts,
        consumer_sentiment,

        cpi_mom_pct,
        unemployment_rate_mom_pct,
        gdp_mom_pct,
        fed_funds_rate_mom_pct,
        housing_starts_mom_pct,
        consumer_sentiment_mom_pct,

        cpi_3m_avg,
        unemployment_rate_3m_avg,
        gdp_3m_avg,
        fed_funds_rate_3m_avg,
        housing_starts_3m_avg,
        consumer_sentiment_3m_avg,

        case
            when unemployment_rate_3m_avg > unemployment_3m_avg_lag3
            then true else false
        end as flag_unemployment_rising,

        case
            when gdp_mom_pct < 0 then true else false
        end as flag_gdp_contracting,

        -- year-over-year CPI change annualised from 3m avg
        case
            when (cpi_3m_avg / lag(cpi_3m_avg, 12) over (order by date) - 1) * 100 > 3
            then true else false
        end as flag_inflation_elevated,

        case
            when fed_funds_rate > 4 then true else false
        end as flag_fed_rate_elevated,

        case
            when housing_starts_mom_pct < 0 then true else false
        end as flag_housing_declining,

        case
            when consumer_sentiment_mom_pct < 0 then true else false
        end as flag_sentiment_falling

    from lagged

)

select
    *,

    (
        cast(flag_unemployment_rising  as int)
        + cast(flag_gdp_contracting    as int)
        + cast(flag_inflation_elevated as int)
        + cast(flag_fed_rate_elevated  as int)
        + cast(flag_housing_declining  as int)
        + cast(flag_sentiment_falling  as int)
    ) as signal_score,

    case
        when (
            cast(flag_unemployment_rising  as int)
            + cast(flag_gdp_contracting    as int)
            + cast(flag_inflation_elevated as int)
            + cast(flag_fed_rate_elevated  as int)
            + cast(flag_housing_declining  as int)
            + cast(flag_sentiment_falling  as int)
        ) >= 3
        then true else false
    end as recession_watch

from flagged
order by date
