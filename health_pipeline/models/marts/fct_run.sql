-- fct_run
-- One row per Strava running activity (Run, TrailRun).
-- Extends fct_activity with run-specific derived columns:
--   - pace in min/km and min/mile
--   - grade-adjusted pace (from Strava's GAP estimate)
--   - pace per heart-rate-bpm (aerobic efficiency proxy)
--
-- Activity-level Garmin columns (training load, HR zones) are NULLed when
-- garmin_match_type_compatible = false. Daily readiness context is always included.

with base as (
    select * from {{ ref('fct_activity') }}
    where activity_type in ('Run', 'TrailRun')
)

select
    -- ── identity ──────────────────────────────────────────────────────────────
    activity_id,
    garmin_activity_id,
    activity_date,
    started_at,
    activity_name,
    activity_type,
    from_upload,

    -- ── join quality ──────────────────────────────────────────────────────────
    garmin_activity_matched,
    garmin_match_type_compatible,
    garmin_match_start_diff_s,
    late_start_utc_risk,

    -- ── distance & duration ───────────────────────────────────────────────────
    distance_m,
    distance_km,
    elapsed_time_s,
    moving_time_s,
    elevation_gain_m,
    elevation_loss_m,
    elevation_low_m,
    elevation_high_m,

    -- ── grade ─────────────────────────────────────────────────────────────────
    average_grade_pct,
    max_grade_pct,
    grade_adjusted_distance_m,
    grade_adjusted_distance_m / 1000.0      as grade_adjusted_distance_km,

    -- ── pace ──────────────────────────────────────────────────────────────────
    -- Raw pace (min/km): moving time / distance
    case when distance_km > 0
        then moving_time_s / 60.0 / distance_km
    end                                     as pace_min_per_km,

    case when distance_km > 0
        then moving_time_s / 60.0 / (distance_km / 1.60934)
    end                                     as pace_min_per_mile,

    -- Grade-adjusted pace: uses Strava's GAP distance estimate.
    -- More comparable across hilly vs flat routes — preferred regression target.
    case when grade_adjusted_distance_m > 0
        then moving_time_s / 60.0 / (grade_adjusted_distance_m / 1000.0)
    end                                     as gap_min_per_km,

    -- Speed in km/h
    average_speed_kph,
    max_speed_ms * 3.6                      as max_speed_kph,

    -- ── heart rate ────────────────────────────────────────────────────────────
    average_heart_rate_bpm,
    max_heart_rate_bpm,

    -- Pace per bpm: lower = more aerobically efficient
    -- (minutes per km per heartbeat — tracks cardiac adaptation over time)
    case when average_heart_rate_bpm > 0 and distance_km > 0
        then (moving_time_s / 60.0 / distance_km) / average_heart_rate_bpm
    end                                     as pace_per_bpm,

    -- ── cadence ───────────────────────────────────────────────────────────────
    average_cadence,

    -- ── effort ────────────────────────────────────────────────────────────────
    calories_kcal,
    relative_effort,
    perceived_exertion,
    total_steps,
    athlete_weight_kg,

    -- ── Garmin activity-level (NULLed if type mismatch) ──────────────────────
    case when garmin_match_type_compatible
        then aerobic_training_effect  end   as aerobic_training_effect,
    case when garmin_match_type_compatible
        then anaerobic_training_effect end  as anaerobic_training_effect,
    case when garmin_match_type_compatible
        then training_effect_label    end   as training_effect_label,
    case when garmin_match_type_compatible
        then activity_training_load   end   as activity_training_load,
    case when garmin_match_type_compatible
        then activity_body_battery_change end as activity_body_battery_change,
    case when garmin_match_type_compatible
        then hr_zone_0_s end                as hr_zone_0_s,
    case when garmin_match_type_compatible
        then hr_zone_1_s end                as hr_zone_1_s,
    case when garmin_match_type_compatible
        then hr_zone_2_s end                as hr_zone_2_s,
    case when garmin_match_type_compatible
        then hr_zone_3_s end                as hr_zone_3_s,
    case when garmin_match_type_compatible
        then hr_zone_4_s end                as hr_zone_4_s,
    case when garmin_match_type_compatible
        then hr_zone_5_s end                as hr_zone_5_s,
    case when garmin_match_type_compatible
        then hr_zone_6_s end                as hr_zone_6_s,
    case when garmin_match_type_compatible
        then is_pr end                      as is_pr,

    -- ── same-day readiness (always valid) ─────────────────────────────────────
    readiness_score,
    readiness_level,
    readiness_feedback_short,
    hrv_factor_pct,
    hrv_factor_feedback,
    readiness_hrv_weekly_avg_ms,
    sleep_score_factor_pct,
    sleep_history_factor_pct,
    recovery_time_h,
    recovery_time_factor_pct,
    acwr_factor_pct,
    readiness_acute_load,
    stress_history_factor_pct,
    valid_sleep,

    -- ── same-day sleep ────────────────────────────────────────────────────────
    sleep_score,
    total_sleep_s,
    deep_sleep_s,
    rem_sleep_s,
    light_sleep_s,
    avg_sleep_stress,

    -- ── same-day body battery & stress ────────────────────────────────────────
    body_battery_start_of_day,
    body_battery_highest,
    stress_avg,
    stress_avg_awake,

    -- ── same-day HRV & resting HR ─────────────────────────────────────────────
    hrv_ms,
    hrv_status,
    health_status_resting_hr_bpm,

    -- ── same-day training load ────────────────────────────────────────────────
    acute_load_7d,
    chronic_load_28d,
    acwr,
    acwr_status,
    training_status,
    fitness_level_trend,

    -- ── weather ───────────────────────────────────────────────────────────────
    average_temperature_c,
    weather_temperature_c,
    apparent_temperature_c,
    humidity_fraction,
    wind_speed_ms,
    wind_gust_ms,
    precipitation_intensity,
    cloud_cover_fraction

from base
