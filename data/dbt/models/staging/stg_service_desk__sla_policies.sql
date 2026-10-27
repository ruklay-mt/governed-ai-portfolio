with

source as (
    select * from {{ source('service_desk', 'sd_sla_policies') }}
)

select
    priority,
    response_hours,
    resolution_hours
from source
