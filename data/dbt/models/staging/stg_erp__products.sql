with

source as (
    select * from {{ source('erp', 'erp_products') }}
)

select
    sku,
    product_name,
    category,
    list_price_nzd,
    unit_cost_nzd
from source
