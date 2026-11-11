-- One row per order line, with the store SKU code exactly as the shop sends it.
select
    order_id,
    line_number,
    cast(sku as {{ dbt.type_string() }})                    as store_sku,
    cast(quantity as {{ dbt.type_int() }})                  as quantity,
    cast(unit_price as {{ dbt.type_numeric() }})            as unit_price,
    cast(line_discount as {{ dbt.type_numeric() }})         as line_discount,
    cast(quantity * unit_price - line_discount as {{ dbt.type_numeric() }}) as line_amount
from {{ source('shop', 'raw_shop_order_lines') }}
