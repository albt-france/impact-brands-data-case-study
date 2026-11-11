-- Product & brand mapping for ad campaigns.
-- 1. The brand comes from the ad account (seed ad_accounts), never from the campaign name.
-- 2. The product comes from the rules seed: an exact campaign_id override first, otherwise the
--    longest product token found inside the squashed campaign name, within the account's brand.
-- 3. The brand written at the start of the name is read separately, to flag names with the wrong brand.
with campaigns as (
    select
        platform,
        account_id,
        campaign_id,
        max(campaign_name)  as campaign_name,
        min(ad_date)        as first_ad_date,
        max(ad_date)        as last_ad_date,
        sum(spend_usd)      as total_spend_usd
    from {{ ref('int_ad_spend_daily') }}
    group by platform, account_id, campaign_id
),

accounts as (
    select * from {{ ref('ad_accounts') }}
    where fixed_in_version <= {{ var('fix_version') }}
),

rules as (
    select * from {{ ref('campaign_product_rules') }}
    where fixed_in_version <= {{ var('fix_version') }}
),

campaigns_with_brand as (
    select
        c.*,
        a.brand_code                                    as brand_code,
        {{ squash_text('c.campaign_name') }}            as squashed_name,
        {{ normalize_text('c.campaign_name') }}         as normalized_name
    from campaigns as c
    left join accounts as a
        on a.account_id = c.account_id
),

override_match as (
    select c.campaign_id, r.product_key
    from campaigns_with_brand as c
    inner join rules as r
        on r.campaign_id = c.campaign_id
),

token_match as (
    select
        c.campaign_id,
        r.product_key,
        r.match_token,
        row_number() over (partition by c.campaign_id order by length(r.match_token) desc) as match_rank
    from campaigns_with_brand as c
    inner join rules as r
        on r.brand_code = c.brand_code
        and r.match_token is not null
        and c.squashed_name like {{ dbt.concat(["'%'", 'r.match_token', "'%'"]) }}
),

name_brand as (
    select
        c.campaign_id,
        t.brand_code as name_brand_code,
        row_number() over (partition by c.campaign_id order by length(t.brand_token) desc) as token_rank
    from campaigns_with_brand as c
    inner join {{ ref('brand_name_tokens') }} as t
        on c.normalized_name like {{ dbt.concat(['t.brand_token', "' %'"]) }}
)

select
    c.platform,
    c.account_id,
    c.campaign_id,
    c.campaign_name,
    c.first_ad_date,
    c.last_ad_date,
    c.total_spend_usd,
    c.brand_code,
    coalesce(o.product_key, t.product_key)                   as product_key,
    t.match_token,
    case
        when c.brand_code is null then 'unmapped_account'
        when o.product_key is not null then 'override'
        when t.product_key is not null then 'rule'
        else 'unmapped_campaign'
    end                                                      as mapping_method,
    n.name_brand_code,
    coalesce(n.name_brand_code <> c.brand_code, false)       as is_name_brand_mismatch
from campaigns_with_brand as c
left join override_match as o
    on o.campaign_id = c.campaign_id
left join token_match as t
    on t.campaign_id = c.campaign_id
    and t.match_rank = 1
left join name_brand as n
    on n.campaign_id = c.campaign_id
    and n.token_rank = 1
