-- Operations: one row per brand x month for the subscription base.
-- active_*: documented definition (state = active). naive_*: the subscription tool's ACTIVE status.
-- churn_rate = cancellations in the month / subscription base (not cancelled) at the start of the month.
with daily as (
    select * from {{ ref('fct_subscriptions_daily') }}
),

month_bounds as (
    select
        month_start,
        min(date_day) as first_day,
        max(date_day) as last_day
    from {{ ref('dim_date') }}
    where has_data
    group by month_start
),

snapshots as (
    select
        d.brand_code,
        b.month_start,
        sum(case when d.date_day = b.first_day then 1 else 0 end)                         as base_start,
        sum(case when d.date_day = b.first_day and d.is_active then 1 else 0 end)          as active_start,
        sum(case when d.date_day = b.last_day and d.is_active then 1 else 0 end)           as active_end,
        sum(case when d.date_day = b.last_day and d.is_active_naive then 1 else 0 end)     as naive_active_end,
        sum(case when d.date_day = b.last_day and d.is_paused then 1 else 0 end)           as paused_end,
        sum(case when d.date_day = b.last_day and d.is_past_due then 1 else 0 end)         as past_due_end
    from daily as d
    inner join month_bounds as b
        on d.date_day in (b.first_day, b.last_day)
    group by 1, 2
),

events as (
    select
        sb.brand_code,
        cast({{ dbt.date_trunc('month', 'e.event_date') }} as date)                      as month_start,
        sum(case when e.event_type = 'created' then 1 else 0 end)                         as new_subscriptions,
        sum(case when e.event_type = 'cancelled' and s.cancellation_reason = 'payment_failed' then 1 else 0 end)
                                                                                          as involuntary_cancellations,
        sum(case when e.event_type = 'cancelled' and coalesce(s.cancellation_reason, '') <> 'payment_failed' then 1 else 0 end)
                                                                                          as voluntary_cancellations,
        sum(case when e.event_type = 'reactivated' then 1 else 0 end)                     as reactivations
    from {{ ref('stg_subscriptions__events') }} as e
    inner join {{ ref('stg_subscriptions__subscriptions') }} as s
        on s.subscription_id = e.subscription_id
    left join {{ ref('store_brand') }} as sb
        on sb.store = s.store_code
    where e.event_date <= cast('{{ var("data_end_date") }}' as date)
    group by 1, 2
)

select
    e.brand_code,
    e.month_start,
    coalesce(s.base_start, 0)                                       as base_start,
    coalesce(s.active_start, 0)                                     as active_start,
    coalesce(s.active_end, 0)                                       as active_end,
    coalesce(s.naive_active_end, 0)                                 as naive_active_end,
    coalesce(s.paused_end, 0)                                       as paused_end,
    coalesce(s.past_due_end, 0)                                     as past_due_end,
    e.new_subscriptions,
    e.voluntary_cancellations,
    e.involuntary_cancellations,
    e.voluntary_cancellations + e.involuntary_cancellations         as cancellations,
    e.reactivations,
    case when coalesce(s.base_start, 0) > 0
         then (e.voluntary_cancellations + e.involuntary_cancellations) * 1.0 / s.base_start
    end                                                             as churn_rate
from events as e
left join snapshots as s
    on s.brand_code = e.brand_code and s.month_start = e.month_start
