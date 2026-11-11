-- Order lines with their canonical product (product mapping seed) and units sold.
-- Store SKU codes come in three styles (one code per bottle with a quantity, or one code per bundle),
-- so units = quantity x units_per_item from the mapping.
with mapping as (
    select * from {{ ref('product_mapping') }}
    where source_system = 'shop'
      and fixed_in_version <= {{ var('fix_version') }}
),

lines as (
    select
        l.*,
        o.brand_code,
        o.order_date,
        o.order_month,
        o.currency,
        o.fx_usd_per_unit,
        o.subtotal,
        o.order_total
    from {{ ref('stg_shop__order_lines') }} as l
    inner join {{ ref('int_orders_usd') }} as o
        on o.order_id = l.order_id
)

select
    {{ dbt.concat(['lines.order_id', "'-'", 'cast(lines.line_number as ' ~ dbt.type_string() ~ ')']) }} as order_line_id,
    lines.order_id,
    lines.line_number,
    lines.brand_code,
    lines.order_date,
    lines.order_month,
    lines.store_sku,
    m.product_key,
    m.purchase_type,
    m.product_key is not null                                   as is_mapped,
    lines.quantity,
    lines.quantity * coalesce(m.units_per_item, 1)              as units,
    lines.currency,
    lines.line_amount,
    lines.line_amount * lines.fx_usd_per_unit                   as line_amount_usd,
    -- Share of the order's net total (after discount and shipping) allocated to this line
    case when lines.subtotal > 0
         then lines.line_amount / lines.subtotal * lines.order_total * lines.fx_usd_per_unit
         else 0 end                                             as allocated_revenue_usd
from lines
left join mapping as m
    on m.source_sku = lines.store_sku
