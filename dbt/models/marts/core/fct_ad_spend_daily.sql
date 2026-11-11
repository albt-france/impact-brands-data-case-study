-- One row per campaign x day (ad account date), with brand and product from the mapping.
select
    {{ dbt.concat(['s.platform', "'-'", 's.campaign_id', "'-'", 'cast(s.ad_date as ' ~ dbt.type_string() ~ ')']) }} as ad_spend_id,
    s.ad_date,
    s.platform,
    s.account_id,
    s.account_timezone,
    s.currency,
    s.campaign_id,
    s.campaign_name,
    c.brand_code,
    c.product_key,
    c.mapping_method,
    s.spend,
    s.spend_usd,
    s.impressions,
    s.clicks,
    s.platform_conversions,
    s.platform_conversion_value_usd
from {{ ref('int_ad_spend_daily') }} as s
left join {{ ref('int_campaigns_mapped') }} as c
    on c.campaign_id = s.campaign_id
