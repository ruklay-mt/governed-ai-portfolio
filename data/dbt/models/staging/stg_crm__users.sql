with

source as (
    select * from {{ source('crm', 'crm_users') }}
)

select
    user_id,
    full_name,
    lower(email) as email,
    region,
    title,
    is_active
from source
