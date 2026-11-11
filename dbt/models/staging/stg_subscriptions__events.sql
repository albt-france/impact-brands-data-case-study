-- Subscription event history (UTC) with the reporting date of each event.
select
    event_id,
    subscription_id,
    event_type,
    cast(occurred_at as timestamp)                              as occurred_at_utc,
    {{ utc_to_local_date('cast(occurred_at as timestamp)') }}   as event_date
from {{ source('subscriptions', 'raw_subscription_events') }}
