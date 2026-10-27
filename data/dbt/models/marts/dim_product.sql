-- Unit cost is deliberately not here: cost lives only in fct_sales, where it can be hidden.

select
    sku as product_key,
    product_name,
    category,
    list_price_nzd
from {{ ref('stg_erp__products') }}
