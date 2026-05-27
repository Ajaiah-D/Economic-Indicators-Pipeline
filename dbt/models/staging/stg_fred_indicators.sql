{{
    config(
        materialized='view',
        tags=['staging', 'fred']
    )
}}

-- Casts the raw Parquet output from the PySpark job into clean typed columns.
-- Source: s3://<bucket>/processed/economic_indicators/
-- Use dbt-duckdb + httpfs for local dev, dbt-spark for Databricks.

with source as (

    select
        cast(date as date) as date,

        cast(cpi               as double) as cpi,
        cast(unemployment_rate as double) as unemployment_rate,
        cast(gdp               as double) as gdp,
        cast(fed_funds_rate    as double) as fed_funds_rate,
        cast(housing_starts    as double) as housing_starts,
        cast(consumer_sentiment as double) as consumer_sentiment,

        cast(cpi_mom_pct               as double) as cpi_mom_pct,
        cast(unemployment_rate_mom_pct  as double) as unemployment_rate_mom_pct,
        cast(gdp_mom_pct               as double) as gdp_mom_pct,
        cast(fed_funds_rate_mom_pct    as double) as fed_funds_rate_mom_pct,
        cast(housing_starts_mom_pct    as double) as housing_starts_mom_pct,
        cast(consumer_sentiment_mom_pct as double) as consumer_sentiment_mom_pct,

        cast(cpi_3m_avg               as double) as cpi_3m_avg,
        cast(unemployment_rate_3m_avg  as double) as unemployment_rate_3m_avg,
        cast(gdp_3m_avg               as double) as gdp_3m_avg,
        cast(fed_funds_rate_3m_avg    as double) as fed_funds_rate_3m_avg,
        cast(housing_starts_3m_avg    as double) as housing_starts_3m_avg,
        cast(consumer_sentiment_3m_avg as double) as consumer_sentiment_3m_avg

    from {{ source('fred_raw', 'economic_indicators') }}

)

select *
from source
where date is not null
order by date
