-- Sales and return lines with every amount converted to NZD at the order-date rate.

with

lines as (
    select * from {{ ref('stg_erp__sales_order_lines') }}
),

orders as (
    select * from {{ ref('stg_erp__sales_orders') }}
),

products as (
    select * from {{ ref('stg_erp__products') }}
),

fx as (
    select * from {{ ref('stg_erp__fx_rates') }}
),

joined as (
    select
        lines.order_number,
        lines.line_number,
        orders.order_type as line_type,
        orders.order_date,
        orders.customer_number,
        orders.sales_rep_id,
        lines.sku,
        lines.quantity,
        lines.discount_pct,
        lines.return_reason,
        products.unit_cost_nzd,
        lines.unit_price
        * case when orders.currency = 'AUD' then fx.aud_to_nzd else 1 end as unit_price_nzd
    from lines
    inner join orders on lines.order_number = orders.order_number
    inner join products on lines.sku = products.sku
    left join fx on orders.order_date = fx.rate_date
),

amounts as (
    select
        *,
        quantity * unit_price_nzd as gross_amount_nzd,
        quantity * unit_price_nzd * (1 - discount_pct / 100) as net_amount_nzd,
        quantity * unit_cost_nzd as cost_nzd
    from joined
)

select
    order_number || '-' || line_number as sales_line_key,
    order_number,
    line_number,
    line_type,
    order_date,
    customer_number,
    sales_rep_id,
    sku,
    quantity,
    discount_pct,
    return_reason,
    round(unit_price_nzd, 2) as unit_price_nzd,
    round(gross_amount_nzd, 2) as gross_amount_nzd,
    round(net_amount_nzd, 2) as net_amount_nzd,
    round(cost_nzd, 2) as cost_nzd,
    round(net_amount_nzd - cost_nzd, 2) as margin_nzd
from amounts
