-- fct_ride
-- One row per Strava cycling activity (Ride, VirtualRide, MountainBikeRide, GravelRide).
-- Extends fct_activity with ride-specific derived columns:
--   - power normalized by athlete weight (W/kg)
--   - speed in km/h and mph
--   - effort efficiency ratio (power per HR bpm)
--
-- Activity-level Garmin columns (training load, HR zones) are NULLed when
-- garmin_match_type_compatible = false — a type-mismatched Garmin record
-- tells us nothing about this specific ride. Daily readiness context is
-- always included regardless of Garmin match quality.
--
-- Power note: average_watts and weighted_average_power_w are Strava's
-- speed/gradient/weight model estimates — NOT raw power meter data.
-- garmin_avg_power_w / garmin_norm_power_w are from Garmin's power meter
-- integration (~7% of activities).

with base as (
    select * from {{ ref('fct_activity') }}
    where activity_type in ('Ride', 'VirtualRide', 'MountainBikeRide', 'GravelRide')
)

select
    -- ── identity ──────────────────────────────────────────────────────────────
    activity_id,
    garmin_activity_id,
    activity_date,
    started_at,
    activity_name,
    activity_type,
    activity_gear,
    from_upload,
    commute,

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

    -- ── speed ─────────────────────────────────────────────────────────────────
    average_speed_ms,
    average_speed_kph,
    average_speed_kph / 1.60934             as average_speed_mph,
    max_speed_ms,
    max_speed_ms * 3.6                      as max_speed_kph,

    -- ── grade ─────────────────────────────────────────────────────────────────
    average_grade_pct,
    max_grade_pct,

    -- ── heart rate ────────────────────────────────────────────────────────────
    average_heart_rate_bpm,
    max_heart_rate_bpm,

    -- ── power (Strava model — available for most rides) ───────────────────────
    average_watts,
    weighted_average_power_w,
    total_work_kj,

    -- W/kg using athlete weight logged at time of activity
    case when athlete_weight_kg > 0
        then average_watts / athlete_weight_kg
    end                                     as average_wkg,
    case when athlete_weight_kg > 0
        then weighted_average_power_w / athlete_weight_kg
    end                                     as weighted_average_wkg,

    -- Effort efficiency: watts per bpm (rough proxy for cardiac efficiency)
    case when average_heart_rate_bpm > 0 and average_watts > 0
        then average_watts / average_heart_rate_bpm
    end                                     as watts_per_bpm,

    -- ── power (Garmin power meter — ~7% of rides, NULLed if type mismatch) ────
    case when garmin_match_type_compatible
        then garmin_avg_power_w  end        as garmin_avg_power_w,
    case when garmin_match_type_compatible
        then garmin_norm_power_w end        as garmin_norm_power_w,

    -- ── cadence ───────────────────────────────────────────────────────────────
    average_cadence,
    max_cadence,

    -- ── calories & gear ───────────────────────────────────────────────────────
    calories_kcal,
    relative_effort,
    perceived_exertion,
    athlete_weight_kg,
    bike_weight_kg,

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
    wind_bearing_deg,
    precipitation_intensity,
    cloud_cover_fraction,
    uv_index

from base
