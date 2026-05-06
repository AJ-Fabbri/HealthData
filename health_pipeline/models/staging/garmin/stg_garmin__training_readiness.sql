-- stg_garmin__training_readiness
-- One row per calendar day — the latest intraday assessment is kept.
-- Key transforms:
--   - Deduplicate: keep row with highest timestamp per calendarDate
--   - Filter: drop level = 'NONE' (device onboarding / calibration period)
--   - Cast timestamps from ISO strings to timestamp type

with source as (
    select * from {{ source('garmin', 'garmin__training_readiness') }}
),

-- Deduplicate: keep the latest assessment per calendar day.
-- The "latest" row captures the most complete picture of readiness after
-- post-sleep HRV computation and any post-exercise resets have settled.
deduped as (
    select *,
        row_number() over (
            partition by calendar_date
            order by cast(timestamp as timestamp) desc
        ) as rn
    from source
),

filtered as (
    select * from deduped
    where rn = 1
      -- Drop the 4 NONE-level records that represent device onboarding.
      -- NONE scores are null and meaningless for analysis.
      and level != 'NONE'
),

renamed as (
    select
        -- ── keys ──────────────────────────────────────────────────────────────
        cast(calendar_date as date)             as calendar_date,
        cast(user_profile_pk as integer)        as user_profile_pk,
        cast(device_id as bigint)               as device_id,

        -- ── timestamps ────────────────────────────────────────────────────────
        cast(timestamp as timestamp)            as assessed_at_utc,
        cast(timestamp_local as timestamp)      as assessed_at_local,

        -- ── readiness score ───────────────────────────────────────────────────
        level                                   as readiness_level,
        cast(score as integer)                  as readiness_score,
        feedback_short,
        feedback_long,

        -- ── assessment context ────────────────────────────────────────────────
        input_context,
        cast(valid_sleep as boolean)            as valid_sleep,

        -- ── recovery time factor ──────────────────────────────────────────────
        cast(recovery_time as integer)          as recovery_time_h,
        cast(recovery_time_factor_percent as integer) as recovery_time_factor_pct,
        recovery_time_factor_feedback,

        -- ── HRV factor ────────────────────────────────────────────────────────
        cast(hrv_weekly_average as double)      as hrv_weekly_avg_ms,
        cast(hrv_factor_percent as integer)     as hrv_factor_pct,
        hrv_factor_feedback,

        -- ── sleep factors ─────────────────────────────────────────────────────
        cast(sleep_history_factor_percent as integer) as sleep_history_factor_pct,
        sleep_history_factor_feedback,
        cast(sleep_score_factor_percent as integer)   as sleep_score_factor_pct,
        sleep_score_factor_feedback,

        -- ── ACWR factor ───────────────────────────────────────────────────────
        cast(acwr_factor_percent as integer)    as acwr_factor_pct,
        acwr_factor_feedback,
        cast(acute_load as integer)             as acute_load,

        -- ── stress history factor ─────────────────────────────────────────────
        cast(stress_history_factor_percent as integer) as stress_history_factor_pct,
        stress_history_factor_feedback

    from filtered
)

select * from renamed
