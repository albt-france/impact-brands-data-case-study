-- ALERT: an ad account sends spend but is not declared in seeds/mapping/ad_accounts.csv,
-- so its spend has no brand. New accounts must be mapped on day one.
select
    account_id,
    platform,
    first_seen_date,
    total_spend_usd
from {{ ref('dim_ad_account') }}
where is_in_connector
  and not is_in_mapping
