-- stg_garmin__activities
-- One row per Garmin-recorded activity (summarizedActivities export).
-- Key transforms:
--   - Convert begin_timestamp, start_time_gmt, start_time_local from epoch-ms
--     to proper timestamp columns
--   - Derive UTC offset in hours from (start_time_local - start_time_gmt)
--   - Convert duration / moving_duration / elapsed_duration from ms to seconds
--   - Convert hr_time_in_zone_* from ms to seconds

with source as (
    select * from {{ source('garmin', 'garmin__activities') }}
),

renamed as (
    select
        -- ── keys ──────────────────────────────────────────────────────────────
        cast(activity_id as bigint)             as activity_id,
        cast(user_profile_id as integer)        as user_profile_id,
        cast(device_id as bigint)               as device_id,
        cast(time_zone_id as integer)           as time_zone_id,

        -- ── activity metadata ─────────────────────────────────────────────────
        name                                    as activity_name,
        activity_type,
        sport_type,

        -- ── timestamps (epoch-ms → timestamp) ─────────────────────────────────
        to_timestamp(cast(begin_timestamp as bigint) / 1000.0)
                                                as started_at_utc,
        to_timestamp(cast(start_time_gmt as double) / 1000.0)
                                                as start_time_utc,
        to_timestamp(cast(start_time_local as double) / 1000.0)
                                                as start_time_local,

        -- Inferred UTC offset in fractional hours (e.g., -5.0 for US Eastern)
        (cast(start_time_local as double) - cast(start_time_gmt as double))
            / 3600000.0                         as utc_offset_h,

        -- ── duration (ms → seconds) ───────────────────────────────────────────
        cast(duration as double) / 1000.0       as duration_s,
        cast(moving_duration as double) / 1000.0 as moving_duration_s,
        cast(elapsed_duration as double) / 1000.0 as elapsed_duration_s,

        -- ── distance & speed ──────────────────────────────────────────────────
        cast(distance as double)                as distance_m,
        cast(avg_speed as double)               as avg_speed_ms,
        cast(max_speed as double)               as max_speed_ms,

        -- ── heart rate ────────────────────────────────────────────────────────
        cast(avg_hr as double)                  as avg_hr_bpm,
        cast(max_hr as double)                  as max_hr_bpm,
        cast(min_hr as double)                  as min_hr_bpm,

        -- ── calories ──────────────────────────────────────────────────────────
        cast(calories as double)                as calories_kcal,
        cast(bmr_calories as double)            as bmr_calories_kcal,

        -- ── elevation ─────────────────────────────────────────────────────────
        -- NOTE: raw values appear to be in mm internally for some activities;
        -- verify units in downstream models before publishing
        cast(elevation_gain as double)          as elevation_gain_raw,
        cast(elevation_loss as double)          as elevation_loss_raw,
        cast(min_elevation as double)           as min_elevation_raw,
        cast(max_elevation as double)           as max_elevation_raw,
        cast(max_vertical_speed as double)      as max_vertical_speed_ms,

        -- ── training effect ───────────────────────────────────────────────────
        cast(aerobic_training_effect as double) as aerobic_training_effect,
        cast(anaerobic_training_effect as double) as anaerobic_training_effect,
        training_effect_label,

        -- ── training load & body battery ──────────────────────────────────────
        cast(activity_training_load as double)  as activity_training_load,
        cast(difference_body_battery as integer) as body_battery_change,

        -- ── power (power meter activities only, ~7% of records) ──────────────
        cast(avg_power as double)               as avg_power_w,
        cast(norm_power as double)              as norm_power_w,

        -- ── cadence ───────────────────────────────────────────────────────────
        cast(avg_fractional_cadence as double)  as avg_cadence_half_rpm,
        cast(max_fractional_cadence as double)  as max_cadence_half_rpm,
        cast(avg_run_cadence as double)         as avg_run_cadence_spm,

        -- ── activity details ──────────────────────────────────────────────────
        cast(lap_count as integer)              as lap_count,
        cast(start_latitude as double)          as start_latitude,
        cast(start_longitude as double)         as start_longitude,
        cast(end_latitude as double)            as end_latitude,
        cast(end_longitude as double)           as end_longitude,
        location_name,

        -- ── intensity minutes (weekly running totals) ─────────────────────────
        cast(moderate_intensity_minutes as integer) as moderate_intensity_min_week_to_date,
        cast(vigorous_intensity_minutes as integer) as vigorous_intensity_min_week_to_date,

        -- ── hydration ─────────────────────────────────────────────────────────
        cast(water_estimated as double)         as water_estimated_ml,

        -- ── HR zone time (ms → seconds) ───────────────────────────────────────
        cast(hr_time_in_zone_0 as integer) / 1000 as hr_zone_0_s,
        cast(hr_time_in_zone_1 as integer) / 1000 as hr_zone_1_s,
        cast(hr_time_in_zone_2 as integer) / 1000 as hr_zone_2_s,
        cast(hr_time_in_zone_3 as integer) / 1000 as hr_zone_3_s,
        cast(hr_time_in_zone_4 as integer) / 1000 as hr_zone_4_s,
        cast(hr_time_in_zone_5 as integer) / 1000 as hr_zone_5_s,
        cast(hr_time_in_zone_6 as integer) / 1000 as hr_zone_6_s,

        -- ── flags ─────────────────────────────────────────────────────────────
        cast(pr as boolean)                     as is_pr,
        cast(favorite as boolean)               as is_favorite,
        cast(elevation_corrected as boolean)    as elevation_corrected,
        cast(parent as boolean)                 as is_multisport_parent,
        manufacturer

    from source
)

select * from renamed
