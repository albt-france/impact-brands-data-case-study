-- One row per shop customer, linked to the CRM through the hashed e-mail
-- (the only identifier both systems share).
with orders as (
    select
        customer_id,
        max(customer_email_sha256)                      as email_sha256,
        min(order_date)                                 as first_order_date,
        max(order_date)                                 as last_order_date,
        count(*)                                        as order_count,
        count(distinct brand_code)                      as brand_count,
        sum(order_total_usd)                            as lifetime_gross_usd
    from {{ ref('int_orders_usd') }}
    group by customer_id
),

first_order as (
    select customer_id, brand_code as first_brand_code, ship_country as country
    from (
        select
            customer_id, brand_code, ship_country,
            row_number() over (partition by customer_id order by created_at_utc, order_id) as order_rank
        from {{ ref('int_orders_usd') }}
    ) as ranked
    where order_rank = 1
)

select
    o.customer_id,
    o.email_sha256,
    crm.crm_contact_id,
    crm.marketing_opt_in,
    f.first_brand_code,
    f.country,
    o.first_order_date,
    o.last_order_date,
    o.order_count,
    o.brand_count,
    o.brand_count > 1                                   as is_multi_brand,
    o.lifetime_gross_usd
from orders as o
inner join first_order as f
    on f.customer_id = o.customer_id
left join {{ ref('stg_crm__customers') }} as crm
    on crm.email_sha256 = o.email_sha256
