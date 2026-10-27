with

tickets as (
    select * from {{ ref('int_tickets_sla') }}
),

customers as (
    select
        customer_number,
        region
    from {{ ref('stg_erp__customers') }}
)

select
    tickets.ticket_id as ticket_key,
    tickets.customer_number as customer_key,
    customers.region,
    tickets.sku as product_key,
    tickets.opened_at,
    tickets.opened_at::date as opened_date,
    tickets.priority,
    tickets.category,
    tickets.subject,
    tickets.description,
    tickets.status,
    tickets.first_response_at,
    tickets.resolved_at,
    round(tickets.response_hours::numeric, 2) as response_hours,
    round(tickets.resolution_hours::numeric, 2) as resolution_hours,
    tickets.sla_resolution_hours,
    tickets.is_sla_breached
from tickets
inner join customers on tickets.customer_number = customers.customer_number
