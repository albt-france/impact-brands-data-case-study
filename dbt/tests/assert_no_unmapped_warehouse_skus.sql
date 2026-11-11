-- ALERT: the 3PL shipped an item code that the product mapping does not know.
with mapping as (
    select source_sku from {{ ref('product_mapping') }}
    where source_system = 'warehouse'
      and fixed_in_version <= {{ var('fix_version') }}
)

select
    s.warehouse_sku,
    min(s.shipped_at_utc)               as first_shipped_at_utc,
    sum(s.units_shipped)                as units_shipped
from {{ ref('stg_fulfillment__shipments') }} as s
left join mapping as m
    on m.source_sku = s.warehouse_sku
where m.source_sku is null
group by s.warehouse_sku
