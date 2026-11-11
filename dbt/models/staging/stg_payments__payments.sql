-- One row per money movement at the payment provider: charge, refund or chargeback.
-- Fixes applied here: epoch seconds -> UTC timestamp, cents -> currency units, upper-case currency.
-- Refunds and chargebacks are negative amounts.
select
    payment_id,
    order_id,
    type                                                    as payment_type,
    processor,
    upper(currency)                                         as currency,
    cast(amount as {{ dbt.type_numeric() }}) / 100          as amount,
    cast(fee as {{ dbt.type_numeric() }}) / 100             as fee,
    {{ epoch_to_utc('created') }}                           as created_at_utc,
    {{ utc_to_local_date(epoch_to_utc('created')) }}        as payment_date,
    payout_id,
    related_payment_id,
    import_batch
from {{ source('payments', 'raw_payments') }}
