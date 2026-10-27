-- Raw source tables (spec §5.1), loaded as-is by data/generator.
-- No constraints beyond primary keys: raw data is allowed to be messy; dbt staging cleans it.

create table if not exists raw.erp_customers (
    customer_number text primary key,
    customer_name text not null,
    region text not null,
    city text not null,
    currency text not null,
    segment text not null,
    credit_limit numeric(14, 2) not null,
    contact_name text,
    contact_email text,
    contact_phone text,
    created_on date not null,
    deleted_at timestamptz,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.erp_products (
    sku text primary key,
    product_name text not null,
    category text not null,
    list_price_nzd numeric(12, 2) not null,
    unit_cost_nzd numeric(12, 2) not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.erp_sales_orders (
    order_number text primary key,
    order_type text not null,
    customer_number text not null,
    sales_rep_id integer not null,
    order_date date not null,
    currency text not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.erp_sales_order_lines (
    order_number text not null,
    line_number integer not null,
    sku text not null,
    quantity integer not null,
    unit_price numeric(12, 2) not null,
    discount_pct numeric(5, 2) not null,
    return_reason text,
    _loaded_at timestamptz not null default now(),
    primary key (order_number, line_number)
);

create table if not exists raw.erp_invoices (
    invoice_number text primary key,
    order_number text not null,
    customer_number text not null,
    invoice_date date not null,
    due_date date not null,
    currency text not null,
    amount_excl_tax numeric(14, 2) not null,
    tax_amount numeric(14, 2) not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.erp_payments (
    payment_id text primary key,
    invoice_number text not null,
    payment_date date not null,
    amount numeric(14, 2) not null,
    currency text not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.ref_fx_rates (
    rate_date date primary key,
    aud_to_nzd numeric(10, 6) not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.crm_users (
    user_id integer primary key,
    full_name text not null,
    email text not null,
    region text not null,
    title text not null,
    is_active boolean not null,
    _loaded_at timestamptz not null default now()
);

-- erp_customer_ref is entered by hand in the CRM, so its format varies and it is sometimes missing.
create table if not exists raw.crm_accounts (
    account_id text primary key,
    account_name text not null,
    erp_customer_ref text,
    owner_user_id integer not null,
    region text not null,
    industry text not null,
    created_on date not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.sd_sla_policies (
    priority text primary key,
    response_hours integer not null,
    resolution_hours integer not null,
    _loaded_at timestamptz not null default now()
);

create table if not exists raw.sd_tickets (
    ticket_id text primary key,
    customer_number text not null,
    sku text,
    opened_at timestamptz not null,
    priority text not null,
    category text not null,
    subject text not null,
    description text not null,
    status text not null,
    first_response_at timestamptz,
    resolved_at timestamptz,
    _loaded_at timestamptz not null default now()
);
