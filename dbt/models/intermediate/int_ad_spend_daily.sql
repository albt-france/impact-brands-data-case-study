-- All ad platforms in one shape, at campaign x day (account date), with spend converted to USD.
with unioned as (
    select platform, ad_date, account_id, currency, account_timezone, campaign_id, campaign_name,
           spend, impressions, clicks, platform_conversions, platform_conversion_value
    from {{ ref('stg_ads__meta') }}
    union all
    select platform, ad_date, account_id, currency, account_timezone, campaign_id, campaign_name,
           spend, impressions, clicks, platform_conversions, platform_conversion_value
    from {{ ref('stg_ads__google') }}
),

campaign_day as (
    -- Meta comes at ad set level: sum the ad sets of each campaign
    select
        platform, ad_date, account_id, currency, account_timezone, campaign_id,
        max(campaign_name)                  as campaign_name,
        sum(spend)                          as spend,
        sum(impressions)                    as impressions,
        sum(clicks)                         as clicks,
        sum(platform_conversions)           as platform_conversions,
        sum(platform_conversion_value)      as platform_conversion_value
    from unioned
    group by platform, ad_date, account_id, currency, account_timezone, campaign_id
)

select
    c.*,
    c.spend * fx.usd_per_unit                       as spend_usd,
    c.platform_conversion_value * fx.usd_per_unit   as platform_conversion_value_usd
from campaign_day as c
left join {{ ref('stg_reference__fx_rates') }} as fx
    on fx.currency = c.currency
    and fx.month_start = {{ dbt.date_trunc('month', 'c.ad_date') }}
