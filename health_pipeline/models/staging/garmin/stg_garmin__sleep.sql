-- stg_garmin__sleep
-- One row per night of sleep. sleepScores sub-object already flattened by ingest.py.
-- Key transforms:
--   - Filter: drop OFF_WRIST and UNCONFIRMED records (not quality-controlled)
--   - Cast timestamps to timestamp type
--   - Derive total_sleep_seconds (deep + light + REM) for convenience

with source as (
    select * from {{ source('garmin', 'garmin__sleep') }}
),

filtered as (
    select * from source
    -- Quality gate: exclude off-wrist and unconfirmed records
    where coalesce(sleep_window_confirmation_type, '') not in ('OFF_WRIST', 'UNCONFIRMED')
),

renamed as (
    select
        -- ── keys ──────────────────────────────────────────────────────────────
        cast(calendar_date as date)                 as calendar_date,

        -- ── timestamps ────────────────────────────────────────────────────────
        cast(sleep_start_timestamp_gmt as timestamp) as sleep_start_utc,
        cast(sleep_end_timestamp_gmt as timestamp)   as sleep_end_utc,

        -- ── quality tier ──────────────────────────────────────────────────────
        sleep_window_confirmation_type,
        cast(retro as boolean)                       as retro,

        -- ── sleep stage durations (seconds) ───────────────────────────────────
        cast(deep_sleep_seconds as integer)          as deep_sleep_s,
        cast(light_sleep_seconds as integer)         as light_sleep_s,
        cast(rem_sleep_seconds as integer)           as rem_sleep_s,
        cast(awake_sleep_seconds as integer)         as awake_s,
        cast(unmeasurable_seconds as integer)        as unmeasurable_s,

        -- Derived: total time asleep (excludes awake within the sleep window)
        cast(deep_sleep_seconds as integer)
            + cast(light_sleep_seconds as integer)
            + coalesce(cast(rem_sleep_seconds as integer), 0)
            as total_sleep_s,

        -- ── enhanced metrics (available ~2022+, ~38% of records) ──────────────
        cast(awake_count as integer)                 as awake_count,
        cast(avg_sleep_stress as double)             as avg_sleep_stress,
        cast(restless_moment_count as integer)       as restless_moment_count,
        cast(average_respiration as double)          as avg_respiration_brpm,
        cast(lowest_respiration as double)           as lowest_respiration_brpm,
        cast(highest_respiration as double)          as highest_respiration_brpm,

        -- ── sleep scores (available ~Apr 2022+, ~62% of records) ─────────────
        cast(sleep_score_overall as integer)         as sleep_score,
        cast(sleep_score_quality as integer)         as sleep_score_quality,
        cast(sleep_score_duration as integer)        as sleep_score_duration,
        cast(sleep_score_recovery as integer)        as sleep_score_recovery,
        cast(sleep_score_deep as integer)            as sleep_score_deep,
        cast(sleep_score_rem as integer)             as sleep_score_rem,
        cast(sleep_score_light as integer)           as sleep_score_light,
        cast(sleep_score_awakenings_count as integer) as sleep_score_awakenings,
        cast(sleep_score_awake_time as integer)      as sleep_score_awake_time,
        cast(sleep_score_combined_awake as integer)  as sleep_score_combined_awake,
        cast(sleep_score_restfulness as integer)     as sleep_score_restfulness,
        cast(sleep_score_interruptions as integer)   as sleep_score_interruptions,
        sleep_score_feedback,
        sleep_score_insight

    from filtered
)

select * from renamed
