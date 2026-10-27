with

source as (
    select * from {{ source('crm', 'crm_accounts') }}
)

select
    account_id,
    trim(account_name) as account_name,
    nullif(trim(erp_customer_ref), '') as erp_customer_ref,
    owner_user_id,
    region,
    industry,
    created_on
from source
