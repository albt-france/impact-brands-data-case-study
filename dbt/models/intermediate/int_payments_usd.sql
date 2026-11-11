-- Payments converted to USD at the rate of the payment month, with the order they belong to.
select
    p.*,
    o.brand_code,
    o.order_date,
    o.order_month,
    {{ dbt.date_trunc('month', 'p.payment_date') }}     as payment_month,
    p.amount * fx.usd_per_unit                          as amount_usd,
    p.fee * fx.usd_per_unit                             as fee_usd
from {{ ref('stg_payments__payments') }} as p
left join {{ ref('int_orders_usd') }} as o
    on o.order_id = p.order_id
left join {{ ref('stg_reference__fx_rates') }} as fx
    on fx.currency = p.currency
    and fx.month_start = {{ dbt.date_trunc('month', 'p.payment_date') }}
