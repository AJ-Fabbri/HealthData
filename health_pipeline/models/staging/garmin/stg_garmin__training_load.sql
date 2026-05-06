-- stg_garmin__training_load
-- One row per calendar day — acute (7-day) and chronic (28-day) training load
-- with ACWR status. The ACWR is the primary overtraining-risk signal.
-- Key transforms:
--   - calendar_date and timestamp are Unix epoch milliseconds → convert to date/timestamp
--   - Deduplicate to one row per calendar_date (keep latest timestamp)
--   - Filter: drop NONE-status rows (start of tracking window, ~6 records)

with source as (
    select * from {{ source('garmin', 'garmin__training_load') }}
),

-- Convert epoch-ms timestamps before deduplication
converted as (
    select *,
        cast(to_timestamp(cast(calendar_date as bigint) / 1000.0) as date) as calendar_date_d,
        to_timestamp(cast(timestamp as bigint) / 1000.0)                   as assessed_at_utc
    from source
),

deduped as (
    select *,
        row_number() over (
            partition by calendar_date_d
            order by assessed_at_utc desc
        ) as rn
    from converted
),

renamed as (
    select
        calendar_date_d                                 as calendar_date,
        cast(user_profile_pk as integer)               as user_profile_pk,
        cast(device_id as bigint)                      as device_id,
        assessed_at_utc,

        -- ── training load ─────────────────────────────────────────────────────
        cast(daily_training_load_acute as integer)     as acute_load_7d,
        cast(daily_training_load_chronic as integer)   as chronic_load_28d,

        -- ── ACWR ──────────────────────────────────────────────────────────────
        cast(daily_acute_chronic_workload_ratio as double) as acwr,
        cast(acwr_percent as integer)                  as acwr_pct,
        -- NONE = start of window (no chronic load yet); LOW = <0.8;
        -- OPTIMAL = 0.8–1.3; HIGH = 1.3–1.5; VERY_HIGH = >1.5
        acwr_status,
        acwr_status_feedback

    from deduped
    where rn = 1
      and acwr_status != 'NONE'
)

select * from renamed
