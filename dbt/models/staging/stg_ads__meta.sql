-- Meta Ads, one row per ad set x day (account time zone, account currency).
-- Fix applied here: a connector re-sync can load the same day twice -> keep the latest load.
with source as (
    select * from {{ source('ads', 'raw_meta_ads') }}
    {% if var('fix_version') == 0 %}
    -- Replay of the warehouse BEFORE the fixes: the backfill of the new account was not loaded yet.
    where _load_batch != 'backfill'
    {% endif %}
),

deduplicated as (
    select
        *,
        row_number() over (partition by date_start, adset_id order by _loaded_at desc) as load_rank
    from source
)

select
    'meta'                                                  as platform,
    cast(date_start as date)                                as ad_date,
    account_id,
    account_currency                                        as currency,
    account_timezone,
    cast(campaign_id as {{ dbt.type_string() }})            as campaign_id,
    campaign_name,
    cast(adset_id as {{ dbt.type_string() }})               as adset_id,
    cast(spend as {{ dbt.type_numeric() }})                 as spend,
    cast(impressions as {{ dbt.type_int() }})               as impressions,
    cast(clicks as {{ dbt.type_int() }})                    as clicks,
    cast(actions_purchase as {{ dbt.type_numeric() }})      as platform_conversions,
    cast(action_values_purchase as {{ dbt.type_numeric() }}) as platform_conversion_value,
    cast(_loaded_at as timestamp)                           as loaded_at_utc
from deduplicated
where load_rank = 1
