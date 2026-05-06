-- stg_garmin__daily_summary
-- One row per calendar day of Garmin wellness summary (UDSFile).
-- allDayStress, bodyBattery, respiration, and hydration sub-objects were
-- flattened by ingest.py; this model casts types and converts the one
-- Unix-epoch-ms timestamp field (resting_heart_rate_timestamp_ms).

with source as (
    select * from {{ source('garmin', 'garmin__daily_summary') }}
),

renamed as (
    select
        -- ── keys ──────────────────────────────────────────────────────────────
        cast(calendar_date as date)             as calendar_date,
        cast(user_profile_pk as integer)        as user_profile_pk,
        uuid,

        -- ── wellness day boundaries ───────────────────────────────────────────
        cast(wellness_start_time_gmt as timestamp)  as wellness_start_utc,
        cast(wellness_end_time_gmt as timestamp)    as wellness_end_utc,
        cast(wellness_start_time_local as timestamp) as wellness_start_local,
        cast(wellness_end_time_local as timestamp)  as wellness_end_local,

        -- ── steps & distance ──────────────────────────────────────────────────
        cast(total_steps as integer)            as total_steps,
        cast(daily_step_goal as integer)        as daily_step_goal,
        cast(total_distance_meters as integer)  as total_distance_m,
        cast(wellness_distance_meters as integer) as wellness_distance_m,

        -- ── calories ──────────────────────────────────────────────────────────
        cast(total_kilocalories as double)      as total_kcal,
        cast(active_kilocalories as double)     as active_kcal,
        cast(bmr_kilocalories as double)        as bmr_kcal,
        cast(remaining_kilocalories as double)  as remaining_kcal,
        cast(net_calorie_goal as integer)       as net_calorie_goal,

        -- ── activity intensity ────────────────────────────────────────────────
        cast(highly_active_seconds as integer)  as highly_active_s,
        cast(active_seconds as integer)         as active_s,
        -- NOTE: these are CUMULATIVE within the current week, reset each Monday
        cast(moderate_intensity_minutes as integer) as moderate_intensity_min_week_to_date,
        cast(vigorous_intensity_minutes as integer) as vigorous_intensity_min_week_to_date,
        cast(is_vigorous_day as boolean)        as is_vigorous_day,
        cast(user_intensity_minutes_goal as integer) as intensity_minutes_weekly_goal,

        -- ── floors ────────────────────────────────────────────────────────────
        cast(floors_ascended_in_meters as double)  as floors_ascended_m,
        cast(floors_descended_in_meters as double) as floors_descended_m,
        cast(user_floors_ascended_goal as integer) as floors_goal,

        -- ── heart rate ────────────────────────────────────────────────────────
        cast(min_heart_rate as integer)         as min_hr_bpm,
        cast(max_heart_rate as integer)         as max_hr_bpm,
        cast(resting_heart_rate as integer)     as resting_hr_bpm,          -- 7-day rolling avg
        cast(current_day_resting_heart_rate as integer) as current_resting_hr_bpm, -- same-day
        cast(min_avg_heart_rate as integer)     as min_5min_avg_hr_bpm,
        cast(max_avg_heart_rate as integer)     as max_5min_avg_hr_bpm,
        -- Convert epoch-ms to timestamp
        to_timestamp(resting_heart_rate_timestamp_ms / 1000.0)
                                                as resting_hr_measured_at,

        -- ── altitude ──────────────────────────────────────────────────────────
        cast(average_monitoring_environment_altitude as double) as avg_altitude_m,

        -- ── stress (allDayStress — TOTAL aggregator) ──────────────────────────
        cast(stress_avg_total as integer)       as stress_avg,
        cast(stress_max_total as integer)       as stress_max,
        cast(stress_duration_total_s as integer) as stress_duration_s,
        cast(stress_rest_duration_total_s as integer) as stress_rest_duration_s,
        cast(stress_avg_awake as integer)       as stress_avg_awake,

        -- ── body battery ──────────────────────────────────────────────────────
        cast(body_battery_charged as integer)   as body_battery_charged,
        cast(body_battery_drained as integer)   as body_battery_drained,
        cast(body_battery_highest as integer)   as body_battery_highest,
        cast(body_battery_lowest as integer)    as body_battery_lowest,
        cast(body_battery_start_of_day as integer) as body_battery_start_of_day,
        cast(body_battery_end_of_day as integer)   as body_battery_end_of_day,
        cast(body_battery_sleep_start as integer)  as body_battery_sleep_start,
        cast(body_battery_sleep_end as integer)    as body_battery_sleep_end,
        cast(body_battery_during_sleep as integer) as body_battery_gained_during_sleep,

        -- ── respiration ───────────────────────────────────────────────────────
        cast(avg_waking_respiration as double)  as avg_waking_respiration_brpm,
        cast(highest_respiration as double)     as highest_respiration_brpm,
        cast(lowest_respiration as double)      as lowest_respiration_brpm,
        cast(latest_respiration as double)      as latest_respiration_brpm,
        cast(latest_respiration_time_gmt as timestamp) as latest_respiration_at_utc,

        -- ── hydration (user-logged; frequently 0 if not tracked) ─────────────
        cast(hydration_value_ml as double)      as hydration_logged_ml,
        cast(hydration_goal_ml as double)       as hydration_goal_ml,
        cast(hydration_sweat_loss_ml as double) as hydration_sweat_loss_ml,
        cast(hydration_adjusted_goal_ml as double) as hydration_adjusted_goal_ml,

        -- ── data-presence flags ───────────────────────────────────────────────
        cast(includes_wellness_data as boolean)      as includes_wellness_data,
        cast(includes_activity_data as boolean)      as includes_activity_data,
        cast(includes_calorie_consumed_data as boolean) as includes_calorie_consumed_data

    from source
)

select * from renamed
