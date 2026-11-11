-- ALERT: a campaign with spend could not be matched to a product
-- (typo in the name, new naming pattern, or a product without a rule).
select
    platform,
    account_id,
    campaign_id,
    campaign_name,
    brand_code,
    first_ad_date,
    total_spend_usd
from {{ ref('int_campaigns_mapped') }}
where mapping_method = 'unmapped_campaign'
  and total_spend_usd > 0
