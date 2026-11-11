-- One row per order: what the shop says it charged vs what the payment provider moved.
-- Used by fct_orders (refunds, net revenue) and by the orders-vs-payments reconciliation test.
with payments as (
    select
        order_id,
        sum(case when payment_type = 'charge' then amount else 0 end)          as charged_amount,
        sum(case when payment_type = 'refund' then -amount else 0 end)         as refunded_amount,
        sum(case when payment_type = 'chargeback' then -amount else 0 end)     as chargeback_amount,
        sum(case when payment_type = 'charge' then amount_usd else 0 end)      as charged_usd,
        sum(case when payment_type = 'refund' then -amount_usd else 0 end)     as refunded_usd,
        sum(case when payment_type = 'chargeback' then -amount_usd else 0 end) as chargeback_usd,
        sum(fee_usd)                                                          as fees_usd,
        sum(case when payment_type = 'charge' then 1 else 0 end)              as charge_count,
        max(case when payment_type = 'charge' then currency end)              as payment_currency
    from {{ ref('int_payments_usd') }}
    group by order_id
)

select
    o.order_id,
    o.brand_code,
    o.order_date,
    o.currency                                          as order_currency,
    o.order_total,
    coalesce(p.charged_amount, 0)                       as charged_amount,
    coalesce(p.refunded_amount, 0)                      as refunded_amount,
    coalesce(p.chargeback_amount, 0)                    as chargeback_amount,
    coalesce(p.charged_usd, 0)                          as charged_usd,
    coalesce(p.refunded_usd, 0)                         as refunded_usd,
    coalesce(p.chargeback_usd, 0)                       as chargeback_usd,
    coalesce(p.fees_usd, 0)                             as fees_usd,
    coalesce(p.charge_count, 0)                         as charge_count,
    p.payment_currency,
    o.order_total - coalesce(p.charged_amount, 0)      as unexplained_difference
from {{ ref('int_orders_usd') }} as o
left join payments as p
    on p.order_id = o.order_id
