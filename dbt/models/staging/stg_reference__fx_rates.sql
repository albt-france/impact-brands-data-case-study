-- Monthly FX rates (USD per 1 unit of currency), with the month as a real date.
select
    cast({{ dbt.concat(['month', "'-01'"]) }} as date)      as month_start,
    upper(currency)                                         as currency,
    cast(usd_per_unit as {{ dbt.type_numeric() }})          as usd_per_unit
from {{ ref('fx_rates_monthly') }}
