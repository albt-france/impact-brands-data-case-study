-- ALERT: a store SKU was sold but has no row in seeds/mapping/product_mapping.csv.
-- Typical cause: a new product (or a new bundle code) went live before its mapping was added.
-- Fix at the source: add the SKU to the mapping seed (versioned in Git), never patch the report.
select
    store_sku,
    brand_code,
    min(order_date)                     as first_sale_date,
    count(*)                            as unmapped_lines,
    sum(allocated_revenue_usd)          as unmapped_revenue_usd
from {{ ref('fct_order_lines') }}
where not is_mapped
group by store_sku, brand_code
