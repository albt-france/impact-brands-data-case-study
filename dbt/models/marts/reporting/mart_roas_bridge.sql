-- One row per month (whole group): every step between the ROAS Media Buying sees in the ad
-- platforms and the return Finance sees on net revenue. Used on page 7 of the report.
with spend as (
    select
        cast({{ dbt.date_trunc('month', 'ad_date') }} as date)  as month_start,
        sum(spend_usd)                                          as warehouse_spend_usd,
        sum(platform_conversion_value_usd)                      as platform_reported_value_usd,
        sum(platform_conversions)                               as platform_conversions
    from {{ ref('fct_ad_spend_daily') }}
    group by 1
),

billed as (
    select
        cast({{ dbt.concat(['b.invoice_month', "'-01'"]) }} as date)   as month_start,
        sum(b.invoiced_amount * fx.usd_per_unit)                      as billed_spend_usd
    from {{ ref('stg_ads__billing') }} as b
    left join {{ ref('stg_reference__fx_rates') }} as fx
        on fx.currency = b.currency
        and fx.month_start = cast({{ dbt.concat(['b.invoice_month', "'-01'"]) }} as date)
    group by 1
),

paid_by_account_day as (
    -- first-party orders from paid campaigns, dated like the ad platform (account time zone)
    select
        cast({{ dbt.date_trunc('month', 'ad_date') }} as date)  as month_start,
        sum(first_party_orders)                                 as paid_orders_account_tz,
        sum(first_party_gross_revenue_usd)                      as paid_gross_account_tz_usd
    from {{ ref('mart_media_buying') }}
    group by 1
),

paid_by_business_day as (
    select
        order_month                                             as month_start,
        count(*)                                                as paid_orders,
        sum(gross_revenue_usd)                                  as paid_gross_usd,
        sum(net_revenue_usd)                                    as paid_net_usd
    from {{ ref('fct_orders') }}
    where attributed_platform is not null
    group by 1
),

all_orders as (
    select
        order_month                                             as month_start,
        sum(gross_revenue_usd)                                  as total_gross_usd,
        sum(net_revenue_usd)                                    as total_net_usd
    from {{ ref('fct_orders') }}
    group by 1
),

booked as (
    select
        cast({{ dbt.concat(['revenue_month', "'-01'"]) }} as date)   as month_start,
        booked_net_revenue_usd
    from {{ ref('stg_finance__month_close') }}
)

select
    s.month_start,
    b.billed_spend_usd,
    s.warehouse_spend_usd,
    b.billed_spend_usd - s.warehouse_spend_usd                          as spend_missing_in_warehouse_usd,
    s.platform_conversions,
    s.platform_reported_value_usd,
    pa.paid_orders_account_tz,
    pa.paid_gross_account_tz_usd,
    s.platform_reported_value_usd - pa.paid_gross_account_tz_usd        as step_attribution_window_usd,
    pb.paid_orders,
    pb.paid_gross_usd,
    pa.paid_gross_account_tz_usd - pb.paid_gross_usd                    as step_time_zone_usd,
    pb.paid_net_usd,
    pb.paid_gross_usd - pb.paid_net_usd                                 as step_refunds_chargebacks_usd,
    a.total_gross_usd,
    a.total_net_usd,
    bk.booked_net_revenue_usd,
    s.platform_reported_value_usd / nullif(s.warehouse_spend_usd, 0)    as roas_platform,
    pb.paid_gross_usd / nullif(s.warehouse_spend_usd, 0)                as roas_first_party_gross,
    pb.paid_net_usd / nullif(s.warehouse_spend_usd, 0)                  as roas_first_party_net,
    a.total_net_usd / nullif(s.warehouse_spend_usd, 0)                  as mer
from spend as s
left join billed as b on b.month_start = s.month_start
left join paid_by_account_day as pa on pa.month_start = s.month_start
left join paid_by_business_day as pb on pb.month_start = s.month_start
left join all_orders as a on a.month_start = s.month_start
left join booked as bk on bk.month_start = s.month_start
where s.month_start <= cast('{{ var("data_end_date") }}' as date)
