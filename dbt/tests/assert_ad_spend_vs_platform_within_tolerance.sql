-- ALERT: spend in the warehouse differs from the platform invoice by more than the tolerance
-- (var ad_spend_tolerance_pct, default 1%) for an account and month.
-- Catches connector gaps (missing days, missing accounts) and double loads.
with warehouse as (
    select
        account_id,
        cast({{ dbt.date_trunc('month', 'ad_date') }} as date)        as month_start,
        sum(spend)                                                    as warehouse_spend
    from {{ ref('int_ad_spend_daily') }}
    group by 1, 2
),

billed as (
    select
        account_id,
        cast({{ dbt.concat(['invoice_month', "'-01'"]) }} as date)    as month_start,
        currency,
        invoiced_amount
    from {{ ref('stg_ads__billing') }}
)

select
    b.account_id,
    b.month_start,
    b.currency,
    b.invoiced_amount,
    coalesce(w.warehouse_spend, 0)                                    as warehouse_spend,
    b.invoiced_amount - coalesce(w.warehouse_spend, 0)                as difference
from billed as b
left join warehouse as w
    on w.account_id = b.account_id
    and w.month_start = b.month_start
where abs(b.invoiced_amount - coalesce(w.warehouse_spend, 0))
      > {{ var('ad_spend_tolerance_pct') }} * b.invoiced_amount
