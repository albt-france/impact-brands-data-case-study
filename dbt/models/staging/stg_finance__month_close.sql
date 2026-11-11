-- Net revenue per month as booked by Finance five days after month end (USD).
select
    month                                                   as revenue_month,
    cast(closed_on as date)                                 as closed_on,
    cast(booked_gross_revenue_usd as {{ dbt.type_numeric() }}) as booked_gross_revenue_usd,
    cast(booked_refunds_usd as {{ dbt.type_numeric() }})    as booked_refunds_usd,
    cast(booked_net_revenue_usd as {{ dbt.type_numeric() }}) as booked_net_revenue_usd
from {{ source('finance', 'raw_finance_month_close') }}
