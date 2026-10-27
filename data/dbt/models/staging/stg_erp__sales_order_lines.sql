with

source as (
    select * from {{ source('erp', 'erp_sales_order_lines') }}
)

select
    order_number,
    line_number,
    sku,
    quantity,
    unit_price,
    discount_pct,
    return_reason
from source
