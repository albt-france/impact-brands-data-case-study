-- Finance: one row per brand x month (business time zone).
-- Sales from the shop next to money from the payment provider, refunds and chargebacks by the month
-- they happened, ad spend and MER.
with sales as (
    select
        brand_code,
        order_month                                     as month_start,
        count(*)                                        as orders,
        sum(gross_revenue_usd)                          as gross_revenue_usd,
        sum(net_revenue_usd)                            as net_revenue_by_order_month_usd,
        sum(case when abs(unexplained_difference) > {{ var('payment_tolerance_usd') }} then 1 else 0 end)
                                                        as orders_not_matching_payments
    from {{ ref('fct_orders') }}
    group by 1, 2
),

money as (
    select
        brand_code,
        payment_month                                   as month_start,
        sum(case when payment_type = 'charge' then amount_usd else 0 end)       as charges_usd,
        sum(case when payment_type = 'refund' then -amount_usd else 0 end)      as refunds_usd,
        sum(case when payment_type = 'chargeback' then -amount_usd else 0 end)  as chargebacks_usd,
        sum(case when payment_type <> 'charge' and is_after_order_month then -amount_usd else 0 end)
                                                        as refunds_on_earlier_months_usd,
        sum(fee_usd)                                    as payment_fees_usd
    from {{ ref('fct_payments') }}
    group by 1, 2
),

ads as (
    select
        brand_code,
        cast({{ dbt.date_trunc('month', 'ad_date') }} as date) as month_start,
        sum(spend_usd)                                  as ad_spend_usd
    from {{ ref('fct_ad_spend_daily') }}
    group by 1, 2
)

select
    s.brand_code,
    s.month_start,
    s.orders,
    s.gross_revenue_usd,
    coalesce(m.charges_usd, 0)                                              as charges_usd,
    coalesce(m.charges_usd, 0) - s.gross_revenue_usd                        as charges_minus_sales_usd,
    s.orders_not_matching_payments,
    coalesce(m.refunds_usd, 0)                                              as refunds_usd,
    coalesce(m.chargebacks_usd, 0)                                          as chargebacks_usd,
    coalesce(m.refunds_on_earlier_months_usd, 0)                            as refunds_on_earlier_months_usd,
    coalesce(m.payment_fees_usd, 0)                                         as payment_fees_usd,
    coalesce(m.charges_usd, 0) - coalesce(m.refunds_usd, 0) - coalesce(m.chargebacks_usd, 0)
                                                                            as net_cash_revenue_usd,
    s.net_revenue_by_order_month_usd,
    coalesce(a.ad_spend_usd, 0)                                             as ad_spend_usd
from sales as s
left join money as m
    on m.brand_code = s.brand_code and m.month_start = s.month_start
left join ads as a
    on a.brand_code = s.brand_code and a.month_start = s.month_start
