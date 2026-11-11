{{ config(severity='warn') }}
-- MONITOR: net revenue of a month Finance has already closed keeps moving (late refunds and
-- chargebacks under the 365-day guarantee). Some movement is normal, so the alert fires only when a
-- month moved more than 1 point above the average movement of all closed months.
with current_revenue as (
    select
        order_month                         as month_start,
        sum(net_revenue_usd)                as current_net_revenue_usd
    from {{ ref('fct_orders') }}
    group by 1
),

compared as (
    select
        f.revenue_month,
        f.booked_net_revenue_usd,
        c.current_net_revenue_usd,
        1 - c.current_net_revenue_usd / f.booked_net_revenue_usd   as drift_pct
    from {{ ref('stg_finance__month_close') }} as f
    inner join current_revenue as c
        on c.month_start = cast({{ dbt.concat(['f.revenue_month', "'-01'"]) }} as date)
),

with_average as (
    select
        *,
        avg(drift_pct) over ()              as average_drift_pct
    from compared
)

select *
from with_average
where drift_pct > average_drift_pct + 0.01
