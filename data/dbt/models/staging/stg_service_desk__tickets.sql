with

source as (
    select * from {{ source('service_desk', 'sd_tickets') }}
)

select
    ticket_id,
    customer_number,
    sku,
    opened_at,
    priority,
    category,
    subject,
    description,
    status,
    first_response_at,
    resolved_at
from source
