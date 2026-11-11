# Metric definitions

One definition per metric, written once, used everywhere (dbt marts, Looker Studio, Power BI).
All amounts are in USD, converted at the monthly rate of the month the money moved.
Reporting days and months use the business time zone `America/New_York` (`var('reporting_timezone')`).
The SQL below runs on the dbt marts (DuckDB syntax; the BigQuery version only differs in date literals).

| Metric | Definition | Grain / table |
|---|---|---|
| `active_subscription` | A subscription whose state at the end of the day is **active**: created or renewed, **not paused, no failed payment being retried, not cancelled**. | `fct_subscriptions_daily.is_active` |
| `active_customer` | A customer with at least one order with positive net revenue in the **last 365 days**, or an active subscription that day. | `fct_orders`, `fct_subscriptions_daily` |
| `churned_subscription` | A subscription with a `cancelled` event in the period. Voluntary (customer cancelled) and involuntary (payment failed after retries) are counted separately. A later reactivation is counted as a reactivation, it does not erase the churn. | `stg_subscriptions__events` |
| `churn_rate` | Cancellations in the month ÷ subscription base at the start of the month (every subscription not cancelled: active + paused + past due). | `mart_subscription_health.churn_rate` |
| `net_revenue` | Order total after discounts (incl. shipping) − refunds − chargebacks known today, attached to the **order month**. Finance's cash view (refunds in the month they are paid) is in `mart_finance_reconciliation.net_cash_revenue_usd`. | `fct_orders.net_revenue_usd` |
| `CPA` | Ad spend ÷ **first-party** orders carrying the campaign id in their UTM. The platform CPA (spend ÷ platform conversions) is shown next to it, never instead of it. | `mart_media_buying` |
| `ROAS` | First-party gross revenue of attributed orders ÷ ad spend. Platform ROAS (platform-claimed value ÷ spend) and net ROAS (after refunds) are shown next to it. | `mart_media_buying`, `mart_roas_bridge` |
| `MER` | Marketing efficiency ratio: **total** net revenue (every channel, renewals included) ÷ **total** ad spend, same month. Does not depend on attribution. | `mart_roas_bridge.mer`, `mart_finance_reconciliation` |

## SQL

### active_subscription
```sql
-- Active subscriptions on a given day (documented definition)
select brand_code, count(*) as active_subscriptions
from marts.fct_subscriptions_daily
where date_day = date '2026-09-30'
  and is_active                      -- state = 'active'
group by brand_code;
```
Edge cases:
- **Paused**: not active (no order will ship), still in the base for churn.
- **Payment failed, retries running (past due)**: not active until a retry succeeds; counted as "at risk".
- **Cancelled then reactivated**: active again from the reactivation day; the cancellation still counts as churn in its month.
- The subscription tool's own status says ACTIVE for paused and past-due subscriptions. That naive count was **11,565** on 30 Sep 2026 against **11,035** with this definition: **+4.8%** overstated (SIMULATED).

### active_customer
```sql
with buyers as (
    select distinct customer_id
    from marts.fct_orders
    where net_revenue_usd > 0
      and order_date >  date '2026-09-30' - interval 365 day
      and order_date <= date '2026-09-30'
),
subscribers as (
    select distinct customer_id
    from marts.fct_subscriptions_daily
    where date_day = date '2026-09-30' and is_active
)
select count(*) as active_customers
from (select customer_id from buyers union select customer_id from subscribers) as c;
```
A customer who buys from two brands counts once for the group and once in each brand's view.

### churned_subscription and churn_rate
```sql
select month_start,
       sum(voluntary_cancellations)   as voluntary,
       sum(involuntary_cancellations) as involuntary,
       sum(cancellations) * 1.0 / nullif(sum(base_start), 0) as churn_rate
from marts.mart_subscription_health
group by month_start
order by month_start;
```

### net_revenue
```sql
select order_month,
       sum(gross_revenue_usd)                     as gross_revenue,
       sum(refunded_usd) + sum(chargeback_usd)    as refunds_and_chargebacks,
       sum(net_revenue_usd)                       as net_revenue
from marts.fct_orders
group by order_month;
```
Because of the 365-day money-back guarantee, the net revenue of a closed month keeps going down for months.
`assert_closed_month_revenue_stable` compares it with what Finance booked at close.

### CPA, ROAS, MER
```sql
select ad_month, brand_code,
       sum(spend_usd) / nullif(sum(first_party_orders), 0)                    as cpa,
       sum(spend_usd) / nullif(sum(platform_conversions), 0)                  as cpa_platform,
       sum(first_party_gross_revenue_usd) / nullif(sum(spend_usd), 0)         as roas,
       sum(platform_conversion_value_usd) / nullif(sum(spend_usd), 0)         as roas_platform,
       sum(first_party_net_revenue_usd) / nullif(sum(spend_usd), 0)           as roas_net
from marts.mart_media_buying
group by ad_month, brand_code;

-- MER: all revenue over all spend, no attribution involved
select month_start, mer from marts.mart_roas_bridge order by month_start;
```
Ratios are always computed from summed numerators and denominators, never by averaging daily ratios.
