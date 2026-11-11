-- One row per order.
-- Fixes applied here: webhook replays removed, store local time converted to UTC,
-- reporting date computed in the business time zone, amounts typed.
with source as (
    select * from {{ source('shop', 'raw_shop_orders') }}
),

-- The shop webhook can deliver the same order twice (replay). Keep the first copy received.
deduplicated as (
    select
        *,
        row_number() over (partition by order_id order by _received_at) as copy_number
    from source
)

select
    order_id,
    store                                                   as store_code,
    customer_id,
    customer_email_sha256,
    ship_country,
    upper(currency)                                         as currency,
    cast(subtotal as {{ dbt.type_numeric() }})              as subtotal,
    cast(discount_total as {{ dbt.type_numeric() }})        as discount_total,
    cast(shipping_total as {{ dbt.type_numeric() }})        as shipping_total,
    cast(order_total as {{ dbt.type_numeric() }})           as order_total,
    order_source,
    coalesce(utm_source, 'none')                            as utm_source,
    cast(utm_campaign_id as {{ dbt.type_string() }})        as utm_campaign_id,
    subscription_id,
    order_source = 'subscription_renewal'                   as is_renewal,
    store_timezone,
    cast(created_at as timestamp)                           as created_at_local,
    {{ local_to_utc('created_at', 'store_timezone') }}      as created_at_utc,
    {{ utc_to_local_date(local_to_utc('created_at', 'store_timezone')) }} as order_date
from deduplicated
where copy_number = 1
