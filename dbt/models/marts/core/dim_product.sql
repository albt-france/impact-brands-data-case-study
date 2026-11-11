-- One row per product (canonical key = brand_code:product_slug), from the real public catalogue.
-- Also shows how many source codes point to each product in the mapping seed.
with mapping_counts as (
    select
        product_key,
        sum(case when source_system = 'shop' then 1 else 0 end)      as shop_sku_count,
        sum(case when source_system = 'warehouse' then 1 else 0 end) as warehouse_sku_count
    from {{ ref('product_mapping') }}
    where fixed_in_version <= {{ var('fix_version') }}
    group by product_key
)

select
    {{ dbt.concat(['p.brand_code', "':'", 'p.product_slug']) }}   as product_key,
    p.brand_code,
    p.product_slug,
    p.product_name,
    p.category,
    p.measurement_unit,
    p.is_kit_or_bundle,
    p.list_unit_price,
    p.one_time_price_1,
    p.subscribe_price_1,
    p.lowest_unit_price,
    p.subscribe_discount_pct,
    p.max_discount_vs_list_pct,
    p.has_subscribe_save,
    p.site_rating_value,
    p.site_rating_count,
    p.price_in_page,
    coalesce(m.shop_sku_count, 0)                                   as shop_sku_count,
    coalesce(m.warehouse_sku_count, 0)                              as warehouse_sku_count
from {{ ref('public_catalog_products') }} as p
left join mapping_counts as m
    on m.product_key = {{ dbt.concat(['p.brand_code', "':'", 'p.product_slug']) }}
where not p.is_gift_card
