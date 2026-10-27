-- One CRM account per ERP customer.
-- The CRM's ERP reference is typed by hand ("C-00012", "C00012", "c-12", or missing), so it is
-- normalised to the ERP format; accounts without a reference fall back to an exact name match.
-- Duplicate CRM accounts for the same customer keep the oldest one.

with

accounts as (
    select * from {{ ref('stg_crm__accounts') }}
),

customers as (
    select
        customer_number,
        customer_name
    from {{ ref('stg_erp__customers') }}
),

matched_by_reference as (
    select
        account_id,
        created_on,
        'erp_reference' as match_method,
        'C-' || lpad(regexp_replace(erp_customer_ref, '[^0-9]', '', 'g'), 5, '0') as customer_number
    from accounts
    where erp_customer_ref is not null
),

matched_by_name as (
    select
        accounts.account_id,
        accounts.created_on,
        'customer_name' as match_method,
        customers.customer_number
    from accounts
    inner join customers
        on lower(accounts.account_name) = lower(customers.customer_name)
    where accounts.erp_customer_ref is null
),

all_matches as (
    select * from matched_by_reference
    union all
    select * from matched_by_name
),

ranked as (
    select
        *,
        row_number() over (
            partition by customer_number order by created_on, account_id
        ) as account_rank
    from all_matches
)

select
    customer_number,
    account_id as crm_account_id,
    match_method
from ranked
where account_rank = 1
