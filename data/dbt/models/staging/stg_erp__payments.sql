with

source as (
    select * from {{ source('erp', 'erp_payments') }}
)

select
    payment_id,
    invoice_number,
    payment_date,
    amount,
    currency
from source
