-- stg_garmin__training_status
-- One row per calendar day — Garmin Training Status classification.
-- Indicates whether recent training is productive, maintaining, etc.
-- Key transforms:
--   - Deduplicate: keep latest timestamp per calendar_date
--   - NO_STATUS (2,513 of 3,906 rows) is normal and kept — it means
--     insufficient training history to classify, not an error

with source as (
    select * from {{ source('garmin', 'garmin__training_status') }}
),

deduped as (
    select *,
        row_number() over (
            partition by calendar_date
            order by cast(timestamp as timestamp) desc
        ) as rn
    from source
),

renamed as (
    select
        cast(calendar_date as date)             as calendar_date,
        cast(user_profile_pk as integer)        as user_profile_pk,
        cast(device_id as bigint)               as device_id,
        cast(timestamp as timestamp)            as assessed_at_utc,

        -- NO_STATUS, MAINTAINING, RECOVERY, PRODUCTIVE, STRAINED,
        -- DETRAINING, PEAKING, OVERREACHING, UNPRODUCTIVE
        training_status,

        -- NO_RESULT, NO_CHANGE, INCREASING, DECREASING
        fitness_level_trend,

        training_status2_feedback_phrase        as feedback_phrase

    from deduped
    where rn = 1
)

select * from renamed
