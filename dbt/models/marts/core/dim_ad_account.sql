-- One row per ad account seen in the connectors or declared in the mapping seed.
-- An account seen in the data but missing from the seed has no brand: that is what the
-- "new ad account" test looks for.
with seen as (
    select
        platform,
        account_id,
        max(currency)           as currency,
        max(account_timezone)   as account_timezone,
        min(ad_date)            as first_seen_date,
        max(ad_date)            as last_seen_date,
        sum(spend_usd)          as total_spend_usd
    from {{ ref('int_ad_spend_daily') }}
    group by platform, account_id
),

declared as (
    select * from {{ ref('ad_accounts') }}
    where fixed_in_version <= {{ var('fix_version') }}
)

select
    coalesce(s.account_id, d.account_id)               as account_id,
    coalesce(s.platform, d.platform)                   as platform,
    d.account_name,
    d.brand_code,
    coalesce(s.currency, d.currency)                   as currency,
    coalesce(s.account_timezone, d.account_timezone)   as account_timezone,
    s.first_seen_date,
    s.last_seen_date,
    coalesce(s.total_spend_usd, 0)                     as total_spend_usd,
    d.account_id is not null                           as is_in_mapping,
    s.account_id is not null                           as is_in_connector
from seen as s
full outer join declared as d
    on d.account_id = s.account_id
