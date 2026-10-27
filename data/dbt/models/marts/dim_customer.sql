with

customers as (
    select * from {{ ref('stg_erp__customers') }}
),

key_map as (
    select * from {{ ref('int_customer_key_map') }}
),

accounts as (
    select * from {{ ref('stg_crm__accounts') }}
)

select
    customers.customer_number as customer_key,
    customers.customer_name,
    customers.region,
    customers.city,
    customers.segment,
    customers.currency,
    customers.credit_limit,
    customers.contact_name,
    customers.contact_email,
    customers.contact_phone,
    key_map.crm_account_id,
    accounts.industry,
    accounts.owner_user_id as account_owner_rep_key,
    customers.created_on,
    customers.is_active
from customers
left join key_map on customers.customer_number = key_map.customer_number
left join accounts on key_map.crm_account_id = accounts.account_id
