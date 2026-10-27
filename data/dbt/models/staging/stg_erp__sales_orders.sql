with

source as (
    select * from {{ source('erp', 'erp_sales_orders') }}
)

select
    order_number,
    order_type,
    customer_number,
    sales_rep_id,
    order_date,
    currency
from source
