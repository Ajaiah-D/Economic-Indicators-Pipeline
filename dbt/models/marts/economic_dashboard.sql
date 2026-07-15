{{
    config(
        materialized='table',
        tags=['mart', 'dashboard', 'fred']
    )
}}

-- Final dashboard table. Materialized so Streamlit reads a static snapshot
-- rather than re-running the window functions on every page load.

with trends as (

    select * from {{ ref('int_indicator_trends') }}

)

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

    treasury_10y,
    treasury_3m,
    yield_spread,

    flag_unemployment_rising,
    flag_gdp_contracting,
    flag_inflation_elevated,
    flag_fed_rate_elevated,
    flag_housing_declining,
    flag_sentiment_falling,
    flag_yield_curve_inverted,

    signal_score,
    recession_watch,

    current_timestamp as dbt_updated_at

from trends
order by date
