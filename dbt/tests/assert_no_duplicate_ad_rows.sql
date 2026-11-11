{{ config(severity='warn') }}
-- MONITOR (source): the Meta connector loaded the same ad set and day more than once (re-sync).
-- stg_ads__meta keeps the latest load; this test says which days were affected.
select
    date_start,
    count(*)                    as rows_loaded,
    count(distinct adset_id)    as distinct_adsets
from {{ source('ads', 'raw_meta_ads') }}
group by date_start
having count(*) > count(distinct adset_id)
