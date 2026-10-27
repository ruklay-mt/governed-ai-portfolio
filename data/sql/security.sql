-- Access policy for the marts (spec §6, ADR 0008, ADR 0009).
--
-- dbt rebuilds mart tables, which drops their grants and policies. This script puts them back,
-- and runs (in one transaction) after every `dbt build`. Until it runs, a rebuilt table has no
-- grants at all, so personas can read nothing: it fails closed.
--
-- Row scope: one policy per regional table, reading the caller's region from
-- ops.persona_scope by session_user. A login missing from the mapping sees no rows.
-- Column scope: explicit column lists per persona role. A column dbt adds later stays hidden
-- until it is listed here (the access-control tests compare this against the full matrix).

-- Start from nothing on every mart.
revoke all on all tables in schema marts from r_sales_rep, r_sales_manager, r_finance, r_support;

-- Row-level security on the regional tables -------------------------------------------------

alter table marts.dim_customer enable row level security;
drop policy if exists persona_region_scope on marts.dim_customer;
create policy persona_region_scope on marts.dim_customer
for select
to r_sales_rep, r_sales_manager, r_finance, r_support
using (
    exists (
        select 1
        from ops.persona_scope as ps
        where
            ps.db_user = session_user
            and (ps.region is null or ps.region = dim_customer.region)
    )
);

alter table marts.fct_sales enable row level security;
drop policy if exists persona_region_scope on marts.fct_sales;
create policy persona_region_scope on marts.fct_sales
for select
to r_sales_rep, r_sales_manager, r_finance, r_support
using (
    exists (
        select 1
        from ops.persona_scope as ps
        where
            ps.db_user = session_user
            and (ps.region is null or ps.region = fct_sales.region)
    )
);

alter table marts.fct_invoices enable row level security;
drop policy if exists persona_region_scope on marts.fct_invoices;
create policy persona_region_scope on marts.fct_invoices
for select
to r_sales_rep, r_sales_manager, r_finance, r_support
using (
    exists (
        select 1
        from ops.persona_scope as ps
        where
            ps.db_user = session_user
            and (ps.region is null or ps.region = fct_invoices.region)
    )
);

alter table marts.fct_tickets enable row level security;
drop policy if exists persona_region_scope on marts.fct_tickets;
create policy persona_region_scope on marts.fct_tickets
for select
to r_sales_rep, r_sales_manager, r_finance, r_support
using (
    exists (
        select 1
        from ops.persona_scope as ps
        where
            ps.db_user = session_user
            and (ps.region is null or ps.region = fct_tickets.region)
    )
);

-- Shared dimensions ------------------------------------------------------------------------

grant select on marts.dim_date to r_sales_rep, r_sales_manager, r_finance, r_support;
grant select on marts.dim_product to r_sales_rep, r_sales_manager, r_finance, r_support;
grant select on marts.dim_sales_rep to r_sales_rep, r_sales_manager, r_finance;

-- dim_customer: sales hide credit limits; finance hides contact PII; support sees names only.

grant select (
    customer_key, customer_name, region, city, segment, currency,
    contact_name, contact_email, contact_phone,
    crm_account_id, industry, account_owner_rep_key, created_on, is_active
) on marts.dim_customer to r_sales_rep, r_sales_manager;

grant select (
    customer_key, customer_name, region, city, segment, currency, credit_limit,
    crm_account_id, industry, account_owner_rep_key, created_on, is_active
) on marts.dim_customer to r_finance;

grant select (
    customer_key, customer_name, region, city, is_active
) on marts.dim_customer to r_support;

-- fct_sales: sales roles never see cost or margin; support has no access.

grant select (
    sales_line_key, order_number, line_number, line_type, order_date,
    customer_key, product_key, sales_rep_key, region,
    quantity, unit_price_nzd, discount_pct, gross_amount_nzd, net_amount_nzd, return_reason
) on marts.fct_sales to r_sales_rep, r_sales_manager;

grant select on marts.fct_sales to r_finance;

-- fct_invoices: payment details are finance only.

grant select on marts.fct_invoices to r_finance;

-- fct_tickets: finance cannot read free-text descriptions (they contain contact details).

grant select on marts.fct_tickets to r_sales_rep, r_sales_manager, r_support;

grant select (
    ticket_key, customer_key, region, product_key, opened_at, opened_date,
    priority, category, subject, status, first_response_at, resolved_at,
    response_hours, resolution_hours, sla_resolution_hours, is_sla_breached
) on marts.fct_tickets to r_finance;
