with

source as (
    select * from {{ source('erp', 'erp_customers') }}
),

renamed as (
    select
        customer_number,
        trim(customer_name) as customer_name,
        region,
        city,
        currency,
        segment,
        credit_limit,
        contact_name,
        lower(contact_email) as contact_email,
        contact_phone,
        created_on,
        deleted_at,
        deleted_at is null as is_active
    from source
)

select * from renamed
