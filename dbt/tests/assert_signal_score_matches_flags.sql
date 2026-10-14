-- signal_score must equal the number of active flags, stay within 0-7,
-- and recession_watch must be exactly "score >= 4"
select *
from {{ ref('economic_dashboard') }}
where signal_score != (
        cast(flag_unemployment_rising    as int)
        + cast(flag_gdp_contracting      as int)
        + cast(flag_inflation_elevated   as int)
        + cast(flag_fed_rate_elevated    as int)
        + cast(flag_housing_declining    as int)
        + cast(flag_sentiment_falling    as int)
        + cast(flag_yield_curve_inverted as int)
    )
    or signal_score not between 0 and 7
    or recession_watch != (signal_score >= 4)
