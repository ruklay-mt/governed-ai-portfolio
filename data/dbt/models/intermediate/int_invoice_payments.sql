-- Invoices with what has been paid and how late, as of today.

with

invoices as (
    select * from {{ ref('stg_erp__invoices') }}
),

payments as (
    select
        invoice_number,
        sum(amount) as paid_amount,
        max(payment_date) as paid_date
    from {{ ref('stg_erp__payments') }}
    group by invoice_number
),

fx as (
    select * from {{ ref('stg_erp__fx_rates') }}
),

joined as (
    select
        invoices.*,
        coalesce(payments.paid_amount, 0) as paid_amount,
        payments.paid_date,
        case when invoices.currency = 'AUD' then fx.aud_to_nzd else 1 end as fx_to_nzd
    from invoices
    left join payments on invoices.invoice_number = payments.invoice_number
    left join fx on invoices.invoice_date = fx.rate_date
)

select
    invoice_number,
    order_number,
    customer_number,
    invoice_date,
    due_date,
    currency,
    total_amount,
    paid_amount,
    paid_date,
    round(total_amount * fx_to_nzd, 2) as total_nzd,
    round((total_amount - paid_amount) * fx_to_nzd, 2) as outstanding_nzd,
    paid_date - invoice_date as days_to_pay,
    greatest(coalesce(paid_date, current_date) - due_date, 0) as days_overdue,
    case
        when paid_amount >= total_amount then 'paid'
        when current_date > due_date then 'overdue'
        else 'open'
    end as invoice_status
from joined
