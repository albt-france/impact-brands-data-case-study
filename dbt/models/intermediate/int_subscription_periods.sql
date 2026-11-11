-- Subscription "sessions": the event history turned into periods with one state each.
-- A period starts at an event and ends at the next event of the same subscription.
-- States: active, paused, past_due (a charge failed, retries running), cancelled.
with events as (
    select
        *,
        case event_type
            when 'created'          then 'active'
            when 'charge_succeeded' then 'active'
            when 'resumed'          then 'active'
            when 'reactivated'      then 'active'
            when 'paused'           then 'paused'
            when 'charge_failed'    then 'past_due'
            when 'cancelled'        then 'cancelled'
        end as state
    from {{ ref('stg_subscriptions__events') }}
),

periods as (
    select
        subscription_id,
        event_id,
        event_type                                          as started_by_event,
        state,
        event_date                                          as valid_from,
        lead(event_date) over (
            partition by subscription_id order by occurred_at_utc, event_id
        )                                                   as valid_to       -- exclusive
    from events
)

select
    p.*,
    s.customer_id,
    s.store_code,
    sb.brand_code,
    s.store_sku,
    m.product_key,
    s.interval_days
from periods as p
inner join {{ ref('stg_subscriptions__subscriptions') }} as s
    on s.subscription_id = p.subscription_id
left join {{ ref('store_brand') }} as sb
    on sb.store = s.store_code
left join {{ ref('product_mapping') }} as m
    on m.source_sku = s.store_sku
    and m.source_system = 'shop'
    and m.fixed_in_version <= {{ var('fix_version') }}
-- several events on the same day: only the last one sets the state of that day
where p.valid_to is null or p.valid_to > p.valid_from
