with

invoices as (
    select * from {{ ref('int_invoice_payments') }}
),

customers as (
    select
        customer_number,
        region
    from {{ ref('stg_erp__customers') }}
)

select
    invoices.invoice_number as invoice_key,
    invoices.order_number,
    invoices.customer_number as customer_key,
    customers.region,
    invoices.invoice_date,
    invoices.due_date,
    invoices.currency,
    invoices.total_amount,
    invoices.total_nzd,
    invoices.paid_amount,
    invoices.outstanding_nzd,
    invoices.paid_date,
    invoices.days_to_pay,
    invoices.days_overdue,
    invoices.invoice_status
from invoices
inner join customers on invoices.customer_number = customers.customer_number
