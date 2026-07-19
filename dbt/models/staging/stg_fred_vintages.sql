{{
    config(
        materialized='view',
        tags=['staging', 'fred', 'vintages']
    )
}}

-- Casts the long ALFRED vintage Parquet into typed columns:
-- one row per (series, observation date, release date, published value).

with source as (

    select
        cast(label as varchar) as label,
        cast(series_id as varchar) as series_id,
        cast(date as date) as date,
        cast(release_date as date) as release_date,
        cast(value as double) as value

    from {{ source('fred_raw', 'fred_vintages') }}

)

select *
from source
where date is not null and release_date is not null and value is not null
order by label, date, release_date
