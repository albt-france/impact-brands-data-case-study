-- CRM contacts. Only the SHA-256 hash of the e-mail is ever stored.
select
    crm_contact_id,
    email_sha256,
    signup_brand                                            as signup_brand_code,
    cast(signup_at as date)                                 as signup_date,
    country,
    cast(marketing_opt_in as {{ dbt.type_boolean() }})      as marketing_opt_in
from {{ source('crm', 'raw_crm_customers') }}
