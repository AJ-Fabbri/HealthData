-- stg_garmin__run_race_predictions
-- One row per calendar day — latest set of predicted race finish times.
-- Derived from VO2 max estimate; updates after qualifying running activities.
-- Key transforms:
--   - Deduplicate: keep latest timestamp per calendar_date
--   - Derive human-readable pace columns from raw race times in seconds

with source as (
    select * from {{ source('garmin', 'garmin__run_race_predictions') }}
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
        cast(timestamp as timestamp)            as updated_at_utc,

        -- ── predicted race times (seconds) ────────────────────────────────────
        cast(race_time5_k as integer)           as predicted_5k_s,
        cast(race_time10_k as integer)          as predicted_10k_s,
        cast(race_time_half as integer)         as predicted_half_s,
        cast(race_time_marathon as integer)     as predicted_marathon_s,

        -- ── derived: pace in min/km ────────────────────────────────────────────
        -- 5K = 5.0 km; 10K = 10.0 km; half = 21.0975 km; marathon = 42.195 km
        round(cast(race_time5_k as double) / 60.0 / 5.0, 2)
                                                as predicted_5k_pace_min_per_km,
        round(cast(race_time10_k as double) / 60.0 / 10.0, 2)
                                                as predicted_10k_pace_min_per_km,
        round(cast(race_time_half as double) / 60.0 / 21.0975, 2)
                                                as predicted_half_pace_min_per_km,
        round(cast(race_time_marathon as double) / 60.0 / 42.195, 2)
                                                as predicted_marathon_pace_min_per_km

    from deduped
    where rn = 1
)

select * from renamed
