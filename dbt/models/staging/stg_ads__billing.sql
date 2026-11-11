-- Monthly ad platform invoices (account currency): the external reference for spend.
select
    invoice_id,
    platform,
    account_id,
    month                                                   as invoice_month,
    currency,
    cast(invoiced_amount as {{ dbt.type_numeric() }})       as invoiced_amount
from {{ source('ads', 'raw_ad_billing') }}
