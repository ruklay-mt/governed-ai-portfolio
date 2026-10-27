select
    user_id as sales_rep_key,
    full_name as rep_name,
    email,
    region,
    title,
    is_active
from {{ ref('stg_crm__users') }}
