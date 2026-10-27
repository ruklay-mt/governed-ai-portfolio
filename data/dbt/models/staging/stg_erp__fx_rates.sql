with

source as (
    select * from {{ source('erp', 'ref_fx_rates') }}
)

select
    rate_date,
    aud_to_nzd
from source
