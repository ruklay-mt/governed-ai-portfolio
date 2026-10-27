-- One row per day from the start of history to a year ahead.

with

days as (
    select generate_series(
        date '2023-11-01', current_date + 365, interval '1 day'
    )::date as date_day
)

select
    date_day,
    extract(year from date_day)::int as calendar_year,
    extract(quarter from date_day)::int as calendar_quarter,
    to_char(date_day, 'YYYY-"Q"Q') as quarter_label,
    extract(month from date_day)::int as calendar_month,
    to_char(date_day, 'YYYY-MM') as month_label,
    to_char(date_day, 'FMMonth') as month_name,
    date_trunc('week', date_day)::date as week_start,
    extract(isodow from date_day)::int as day_of_week,
    extract(isodow from date_day) in (6, 7) as is_weekend
from days
