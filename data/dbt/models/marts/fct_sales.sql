-- One row per sales or return line. Returns have negative quantity and amounts.

with

lines as (
    select * from {{ ref('int_sales_lines_nzd') }}
),

customers as (
    select
        customer_number,
        region
    from {{ ref('stg_erp__customers') }}
)

select
    lines.sales_line_key,
    lines.order_number,
    lines.line_number,
    lines.line_type,
    lines.order_date,
    lines.customer_number as customer_key,
    lines.sku as product_key,
    lines.sales_rep_id as sales_rep_key,
    customers.region,
    lines.quantity,
    lines.unit_price_nzd,
    lines.discount_pct,
    lines.gross_amount_nzd,
    lines.net_amount_nzd,
    lines.cost_nzd,
    lines.margin_nzd,
    lines.return_reason
from lines
inner join customers on lines.customer_number = customers.customer_number
