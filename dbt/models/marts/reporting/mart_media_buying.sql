-- Media Buying: one row per campaign x day (in the ad account's own time zone, like the ad platforms).
-- Platform numbers (what Ads Manager shows) next to first-party numbers (real orders carrying the
-- campaign id in their UTM). Ratios (CPA, ROAS) are computed from these sums: see METRICS.md.
with spend as (
    select * from {{ ref('fct_ad_spend_daily') }}
),

campaigns as (
    select c.campaign_id, c.platform, c.account_id, c.campaign_name, c.brand_code, c.product_key,
           c.mapping_method, a.account_timezone
    from {{ ref('int_campaigns_mapped') }} as c
    left join {{ ref('dim_ad_account') }} as a
        on a.account_id = c.account_id
),

orders as (
    -- orders dated in the ad account time zone, so they line up with the platform's day
    select
        o.utm_campaign_id                                                       as campaign_id,
        {{ utc_to_local_date('o.created_at_utc', 'c.account_timezone') }}       as ad_date,
        count(*)                                                                as orders,
        sum(case when o.starts_subscription then 1 else 0 end)                  as subscription_starts,
        sum(o.gross_revenue_usd)                                                as gross_revenue_usd,
        sum(o.net_revenue_usd)                                                  as net_revenue_usd
    from {{ ref('fct_orders') }} as o
    inner join campaigns as c
        on c.campaign_id = o.utm_campaign_id
    group by 1, 2
),

keys as (
    select campaign_id, ad_date from spend
    union distinct
    select campaign_id, ad_date from orders
)

select
    k.ad_date,
    {{ dbt.date_trunc('month', 'k.ad_date') }}                as ad_month,
    c.platform,
    c.account_id,
    c.brand_code,
    c.product_key,
    c.campaign_id,
    c.campaign_name,
    c.mapping_method,
    coalesce(s.spend_usd, 0)                                  as spend_usd,
    coalesce(s.impressions, 0)                                as impressions,
    coalesce(s.clicks, 0)                                     as clicks,
    coalesce(s.platform_conversions, 0)                       as platform_conversions,
    coalesce(s.platform_conversion_value_usd, 0)              as platform_conversion_value_usd,
    coalesce(o.orders, 0)                                     as first_party_orders,
    coalesce(o.subscription_starts, 0)                        as first_party_subscription_starts,
    coalesce(o.gross_revenue_usd, 0)                          as first_party_gross_revenue_usd,
    coalesce(o.net_revenue_usd, 0)                            as first_party_net_revenue_usd
from keys as k
inner join campaigns as c
    on c.campaign_id = k.campaign_id
left join spend as s
    on s.campaign_id = k.campaign_id and s.ad_date = k.ad_date
left join orders as o
    on o.campaign_id = k.campaign_id and o.ad_date = k.ad_date
