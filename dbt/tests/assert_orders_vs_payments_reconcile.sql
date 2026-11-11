{{ config(severity='warn') }}
-- MONITOR: every order should have exactly one charge equal to the order total
-- (within var payment_tolerance_usd). Rows here are open items for the payments team.
select
    order_id,
    brand_code,
    order_date,
    order_currency,
    payment_currency,
    order_total,
    charged_amount,
    charge_count,
    unexplained_difference
from {{ ref('int_order_payments') }}
where abs(unexplained_difference) > {{ var('payment_tolerance_usd') }}
   or charge_count <> 1
