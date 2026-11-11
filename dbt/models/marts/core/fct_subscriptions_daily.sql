-- One row per subscription per day while it is not cancelled.
-- is_active follows the documented definition (METRICS.md): state = 'active'
-- (not paused, no failed payment being retried). is_active_naive is what the subscription
-- tool shows (status ACTIVE), kept side by side to measure the gap.
select
    {{ dbt.concat(['p.subscription_id', "'-'", 'cast(d.date_day as ' ~ dbt.type_string() ~ ')']) }} as subscription_day_id,
    d.date_day,
    d.month_start,
    p.subscription_id,
    p.customer_id,
    p.brand_code,
    p.product_key,
    p.state,
    {% if var('fix_version') == 0 %}
    -- Before the fix the warehouse used the tool's status: everything not cancelled was "active".
    true                                                as is_active,
    {% else %}
    p.state = 'active'                                  as is_active,
    {% endif %}
    true                                                as is_active_naive,
    p.state = 'paused'                                  as is_paused,
    p.state = 'past_due'                                as is_past_due
from {{ ref('int_subscription_periods') }} as p
inner join {{ ref('dim_date') }} as d
    on d.date_day >= p.valid_from
    and (p.valid_to is null or d.date_day < p.valid_to)
    and d.has_data
where p.state <> 'cancelled'
