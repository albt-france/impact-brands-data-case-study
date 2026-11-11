-- Current state of each subscription, as the subscription tool reports it.
-- Careful: the tool's status is only ACTIVE or CANCELLED. Paused and failing subscriptions
-- still show ACTIVE here; the real state comes from the event history (int_subscription_periods).
select
    subscription_id,
    customer_id,
    store                                                   as store_code,
    cast(sku as {{ dbt.type_string() }})                    as store_sku,
    cast(price as {{ dbt.type_numeric() }})                 as price,
    cast(order_interval_frequency as {{ dbt.type_int() }})  as interval_days,
    lower(status)                                           as tool_status,
    cast(created_at as timestamp)                           as created_at_utc,
    cast(cancelled_at as timestamp)                         as cancelled_at_utc,
    cancellation_reason,
    cast(failed_charge_count as {{ dbt.type_int() }})       as failed_charge_count
from {{ source('subscriptions', 'raw_subscriptions') }}
