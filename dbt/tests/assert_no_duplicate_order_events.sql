{{ config(severity='warn') }}
-- MONITOR (source): the shop webhook delivered the same order more than once.
-- stg_shop__orders already keeps one copy; this test says how often it happens.
select
    order_id,
    count(*)            as copies
from {{ source('shop', 'raw_shop_orders') }}
group by order_id
having count(*) > 1
