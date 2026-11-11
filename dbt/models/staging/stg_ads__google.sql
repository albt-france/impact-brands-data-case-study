-- Google Ads, one row per campaign x day (account time zone, account currency).
-- Fix applied here: cost in micros -> currency units.
select
    'google'                                                as platform,
    cast(segments_date as date)                             as ad_date,
    customer_id                                             as account_id,
    customer_currency_code                                  as currency,
    customer_time_zone                                      as account_timezone,
    cast(campaign_id as {{ dbt.type_string() }})            as campaign_id,
    campaign_name,
    cast(null as {{ dbt.type_string() }})                   as adset_id,
    cast(metrics_cost_micros as {{ dbt.type_numeric() }}) / 1000000 as spend,
    cast(metrics_impressions as {{ dbt.type_int() }})       as impressions,
    cast(metrics_clicks as {{ dbt.type_int() }})            as clicks,
    cast(metrics_conversions as {{ dbt.type_numeric() }})   as platform_conversions,
    cast(metrics_conversions_value as {{ dbt.type_numeric() }}) as platform_conversion_value,
    cast(_loaded_at as timestamp)                           as loaded_at_utc
from {{ source('ads', 'raw_google_ads') }}
