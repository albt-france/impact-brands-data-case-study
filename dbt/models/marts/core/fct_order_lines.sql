-- One row per order line, with the canonical product. Unmapped lines keep product_key = null
-- (and are caught by assert_no_unmapped_sales) instead of being dropped.
select
    order_line_id,
    order_id,
    line_number,
    brand_code,
    order_date,
    order_month,
    store_sku,
    product_key,
    is_mapped,
    purchase_type,
    quantity,
    units,
    currency,
    line_amount,
    line_amount_usd,
    allocated_revenue_usd
from {{ ref('int_order_lines_mapped') }}
