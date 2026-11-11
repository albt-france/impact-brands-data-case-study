{{ config(severity='warn') }}
-- MONITOR (source): the subscription tool says ACTIVE but its own event history says the
-- subscription is paused or in payment failure. Reported to the owner of the subscription tool.
with latest as (
    select subscription_id, state
    from (
        select
            subscription_id,
            state,
            row_number() over (partition by subscription_id order by valid_from desc, event_id desc) as rn
        from {{ ref('int_subscription_periods') }}
    ) as ranked
    where rn = 1
)

select
    s.subscription_id,
    s.tool_status,
    l.state             as state_from_events
from {{ ref('stg_subscriptions__subscriptions') }} as s
inner join latest as l
    on l.subscription_id = s.subscription_id
where s.tool_status = 'active'
  and l.state in ('paused', 'past_due')
