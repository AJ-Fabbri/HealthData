-- stg_garmin__vo2max
-- One row per VO2 max estimate update (611 rows, 2020-04-16 – 2026-03-28).
-- Multiple records per calendar_date are possible (one per qualifying activity).
-- NO deduplication here — the full history is preserved so downstream models
-- can choose between "latest per day" or "activity-specific estimates".
-- 88% have null sport/sub_sport (general device estimate, not activity-triggered).

with source as (
    select * from {{ source('garmin', 'garmin__vo2max') }}
),

renamed as (
    select
        cast(calendar_date as date)             as calendar_date,
        cast(user_profile_pk as integer)        as user_profile_pk,
        cast(device_id as bigint)               as device_id,
        cast(update_timestamp as timestamp)     as updated_at_utc,

        -- sport context (88% null = general rolling estimate)
        sport,
        sub_sport,

        -- ── VO2 max estimate ──────────────────────────────────────────────────
        cast(vo2_max_value as double)           as vo2max_ml_kg_min,
        cast(max_met as double)                 as max_met,
        max_met_category,
        cast(calibrated_data as boolean)        as is_calibrated

    from source
)

select * from renamed
