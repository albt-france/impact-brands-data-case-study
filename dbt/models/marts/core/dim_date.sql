-- One row per calendar day. Built from a 0-9999 number sequence so it runs on any warehouse.
with digits as (
    select 0 as d union all select 1 union all select 2 union all select 3 union all select 4
    union all select 5 union all select 6 union all select 7 union all select 8 union all select 9
),

numbers as (
    select a.d + 10 * b.d + 100 * c.d + 1000 * e.d as n
    from digits as a
    cross join digits as b
    cross join digits as c
    cross join digits as e
),

days as (
    select cast({{ dbt.dateadd('day', 'n', "cast('" ~ var('calendar_start') ~ "' as date)") }} as date) as date_day
    from numbers
)

select
    date_day,
    cast({{ dbt.date_trunc('week', 'date_day') }} as date)     as week_start,
    cast({{ dbt.date_trunc('month', 'date_day') }} as date)    as month_start,
    extract(year from date_day)                                as year_number,
    extract(month from date_day)                               as month_number,
    date_day <= cast('{{ var("data_end_date") }}' as date)     as has_data
from days
where date_day <= cast('{{ var("calendar_end") }}' as date)
