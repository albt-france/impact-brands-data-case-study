-- ALERT: the active subscription count must not include paused subscriptions or subscriptions
-- whose payment failed (definition in METRICS.md). Returns the subscriptions counted wrongly.
select
    subscription_id,
    brand_code,
    state,
    min(date_day)       as first_day_counted,
    count(*)            as days_counted_wrongly
from {{ ref('fct_subscriptions_daily') }}
where is_active
  and state <> 'active'
group by subscription_id, brand_code, state
