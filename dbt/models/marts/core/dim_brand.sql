-- One row per brand. Public attributes (PUBLIC DATA) + the store code used by the shop system.
select
    b.brand_code,
    b.brand_name,
    b.focus,
    b.catalogue_products,
    b.snapshot_date                     as catalogue_snapshot_date,
    sb.store                            as store_code
from {{ ref('public_brands') }} as b
left join {{ ref('store_brand') }} as sb
    on sb.brand_code = b.brand_code
