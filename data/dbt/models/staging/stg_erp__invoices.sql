with

source as (
    select * from {{ source('erp', 'erp_invoices') }}
)

select
    invoice_number,
    order_number,
    customer_number,
    invoice_date,
    due_date,
    currency,
    amount_excl_tax,
    tax_amount,
    amount_excl_tax + tax_amount as total_amount
from source
