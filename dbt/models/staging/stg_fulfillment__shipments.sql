-- One row per shipped warehouse item. The 3PL only knows the order number without the
-- store prefix (order_ref) and uses its own SKU codes.
select
    shipment_id,
    cast(order_ref as {{ dbt.type_string() }})              as order_ref,
    cast(warehouse_sku as {{ dbt.type_string() }})          as warehouse_sku,
    cast(quantity as {{ dbt.type_int() }})                  as units_shipped,
    cast(shipped_at_utc as timestamp)                       as shipped_at_utc,
    status                                                  as shipment_status,
    cast(returned_at_utc as timestamp)                      as returned_at_utc
from {{ source('fulfillment', 'raw_fulfillment') }}
