-- Ticket timings against the SLA for their priority.
-- An unresolved ticket counts as breached once it is older than its resolution SLA.

with

tickets as (
    select * from {{ ref('stg_service_desk__tickets') }}
),

policies as (
    select * from {{ ref('stg_service_desk__sla_policies') }}
),

timed as (
    select
        tickets.*,
        policies.response_hours as sla_response_hours,
        policies.resolution_hours as sla_resolution_hours,
        extract(epoch from tickets.first_response_at - tickets.opened_at) / 3600 as response_hours,
        extract(epoch from tickets.resolved_at - tickets.opened_at) / 3600 as resolution_hours,
        extract(epoch from current_timestamp - tickets.opened_at) / 3600 as age_hours
    from tickets
    inner join policies on tickets.priority = policies.priority
)

select
    *,
    coalesce(resolution_hours, age_hours) > sla_resolution_hours as is_sla_breached
from timed
