-- One row per order. Revenue definitions (see METRICS.md):
--   gross_revenue_usd = order total charged (after discount, incl. shipping)
--   net_revenue_usd   = gross - refunds - chargebacks (as known today)
with campaigns as (
    select campaign_id, platform, product_key as campaign_product_key
    from {{ ref('int_campaigns_mapped') }}
)

select
    o.order_id,
    o.order_date,
    o.order_month,
    o.created_at_utc,
    o.brand_code,
    o.customer_id,
    o.ship_country,
    o.currency,
    o.order_source,
    o.utm_source,
    o.utm_campaign_id,
    c.platform                                          as attributed_platform,
    c.campaign_product_key,
    o.is_renewal,
    o.subscription_id,
    o.subscription_id is not null and not o.is_renewal  as starts_subscription,
    o.order_total,
    o.order_total_usd                                   as gross_revenue_usd,
    o.discount_usd,
    o.shipping_usd,
    p.refunded_usd,
    p.chargeback_usd,
    p.fees_usd,
    o.order_total_usd - p.refunded_usd - p.chargeback_usd as net_revenue_usd,
    p.charged_amount,
    p.payment_currency,
    p.unexplained_difference
from {{ ref('int_orders_usd') }} as o
left join {{ ref('int_order_payments') }} as p
    on p.order_id = o.order_id
left join campaigns as c
    on c.campaign_id = o.utm_campaign_id
