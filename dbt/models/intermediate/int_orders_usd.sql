-- Orders with their brand (from the store code) and every amount converted to USD
-- at the monthly rate of the order month.
select
    o.*,
    sb.brand_code,
    {{ dbt.date_trunc('month', 'o.order_date') }}   as order_month,
    fx.usd_per_unit                                 as fx_usd_per_unit,
    o.subtotal * fx.usd_per_unit                    as subtotal_usd,
    o.discount_total * fx.usd_per_unit              as discount_usd,
    o.shipping_total * fx.usd_per_unit              as shipping_usd,
    o.order_total * fx.usd_per_unit                 as order_total_usd
from {{ ref('stg_shop__orders') }} as o
left join {{ ref('store_brand') }} as sb
    on sb.store = o.store_code
left join {{ ref('stg_reference__fx_rates') }} as fx
    on fx.currency = o.currency
    and fx.month_start = {{ dbt.date_trunc('month', 'o.order_date') }}
