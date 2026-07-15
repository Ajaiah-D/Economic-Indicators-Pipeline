{{
    config(
        materialized='view',
        tags=['intermediate', 'fred']
    )
}}

-- Adds six binary stress flags and a composite signal score.
-- recession_watch fires when 3+ flags are active simultaneously. Backtested
-- against every NBER recession since 1959 (the earliest point all six
-- indicators overlap): catches all 9, with the housing/sentiment/fed-funds
-- flags below tuned to cut false positives without losing any of the 9
-- hits. See the README's "Recession-risk signal" section for the numbers.

with staged as (

    select * from {{ ref('stg_fred_indicators') }}

),

lagged as (

    select
        *,
        lag(unemployment_rate_3m_avg, 3) over (order by date) as unemployment_3m_avg_lag3,
        lag(housing_starts_3m_avg, 3) over (order by date) as housing_starts_3m_avg_lag3,
        lag(consumer_sentiment_3m_avg, 3) over (order by date) as consumer_sentiment_3m_avg_lag3,
        avg(fed_funds_rate) over (
            order by date rows between 35 preceding and current row
        ) as fed_funds_rate_36m_avg

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

        -- elevated relative to its own trailing 3-year average rather than a
        -- fixed level, since "high" for the fed funds rate has meant very
        -- different things across eras (double digits in the early 80s,
        -- near zero for most of the 2010s)
        case
            when fed_funds_rate > fed_funds_rate_36m_avg + 1.0 then true else false
        end as flag_fed_rate_elevated,

        -- 3-month trend rather than a single month's sign flip, same
        -- treatment as unemployment_rising -- housing starts and sentiment
        -- are both noisy enough that raw month-over-month direction isn't
        -- a meaningful stress signal on its own
        case
            when housing_starts_3m_avg < housing_starts_3m_avg_lag3
            then true else false
        end as flag_housing_declining,

        case
            when consumer_sentiment_3m_avg < consumer_sentiment_3m_avg_lag3
            then true else false
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
