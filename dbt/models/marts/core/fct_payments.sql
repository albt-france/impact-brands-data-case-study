-- One row per money movement (charge, refund, chargeback), in payment currency and USD.
-- payment_month vs order_month shows when a refund lands in a later month than its sale.
select
    payment_id,
    order_id,
    brand_code,
    payment_type,
    processor,
    currency,
    amount,
    amount_usd,
    fee_usd,
    created_at_utc,
    payment_date,
    payment_month,
    order_date,
    order_month,
    payment_month > order_month                         as is_after_order_month,
    payout_id,
    import_batch
from {{ ref('int_payments_usd') }}
