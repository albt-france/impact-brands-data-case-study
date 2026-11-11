-- ALERT: the brand written at the start of the campaign name is not the brand of the ad account
-- (e.g. a 'PHR_' campaign running on the Pureance account). Campaigns already reviewed and given a
-- campaign-level override in the rules seed are accepted.
select
    platform,
    account_id,
    campaign_id,
    campaign_name,
    brand_code          as account_brand_code,
    name_brand_code
from {{ ref('int_campaigns_mapped') }}
where is_name_brand_mismatch
  and mapping_method <> 'override'
