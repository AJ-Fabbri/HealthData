-- fct_activity
-- One row per Strava activity. Strava is the primary performance spine.
--
-- Joins:
--   1. stg_strava__activities  — performance metrics (power, pace, HR, weather)
--   2. int_garmin__daily       — same-day readiness context (LEFT JOIN on local date)
--   3. stg_garmin__activities  — activity-level training load + HR zones (best-effort
--                                match on same local date + closest start time ≤ 2h)
--
-- Join edge case note:
--   strava.activity_date and garmin.calendar_date are both local-time dates, so they
--   should align correctly for most activities. However, activities starting after 22:00
--   local time may have UTC start times that cross midnight. The flag
--   `late_start_utc_risk` marks these rows so downstream models can validate or exclude
--   them from date-sensitive analyses.

with strava as (
    select * from {{ ref('stg_strava__activities') }}
),

garmin_daily as (
    select * from {{ ref('int_garmin__daily') }}
),

garmin_activity_raw as (
    select * from {{ ref('stg_garmin__activities') }}
),

-- For each Strava activity, find the best-matching Garmin activity.
-- ±1 day window handles UTC/local date boundary crossings (activities near
-- midnight can land on the adjacent date depending on timezone).
-- Rank by: (1) same-day preference, (2) type compatibility, (3) start time closeness.
garmin_activity_candidates as (
    select
        sa.activity_id                              as strava_activity_id,
        ga.activity_id                              as garmin_activity_id,
        ga.aerobic_training_effect,
        ga.anaerobic_training_effect,
        ga.training_effect_label,
        ga.activity_training_load,
        ga.body_battery_change,
        ga.avg_power_w                              as garmin_avg_power_w,
        ga.norm_power_w                             as garmin_norm_power_w,
        ga.hr_zone_0_s,
        ga.hr_zone_1_s,
        ga.hr_zone_2_s,
        ga.hr_zone_3_s,
        ga.hr_zone_4_s,
        ga.hr_zone_5_s,
        ga.hr_zone_6_s,
        ga.is_pr,
        abs(datediff('day', cast(ga.start_time_local as date), sa.activity_date))
                                                    as date_diff_days,
        abs(
            epoch(sa.started_at) - epoch(cast(ga.start_time_local as timestamp))
        )                                           as start_diff_s,
        -- Type compatibility: 0 = compatible, 1 = incompatible
        case
            when sa.activity_type in ('Ride', 'VirtualRide', 'MountainBikeRide', 'GravelRide')
             and ga.activity_type in ('road_biking', 'cycling', 'virtual_ride',
                                      'mountain_biking', 'gravel_cycling',
                                      'indoor_cycling', 'downhill_biking')       then 0
            when sa.activity_type in ('Run', 'TrailRun')
             and ga.activity_type in ('running', 'trail_running',
                                      'treadmill_running', 'indoor_running')     then 0
            when sa.activity_type in ('Walk', 'Hike')
             and ga.activity_type in ('walking', 'hiking')                       then 0
            when sa.activity_type = 'Weight Training'
             and ga.activity_type = 'strength_training'                          then 0
            when sa.activity_type = 'Crossfit'
             and ga.activity_type = 'strength_training'                          then 0
            when sa.activity_type in ('Alpine Ski', 'Backcountry Ski', 'NordicSki')
             and ga.activity_type in ('resort_skiing', 'resort_skiing_snowboarding_ws',
                                      'backcountry_skiing',
                                      'backcountry_skiing_snowboarding_ws',
                                      'cross_country_skiing', 'winter_sports')   then 0
            when sa.activity_type in ('Elliptical', 'Workout')
             and ga.activity_type in ('elliptical', 'indoor_cardio')             then 0
            when sa.activity_type = 'Yoga'
             and ga.activity_type = 'yoga'                                       then 0
            when sa.activity_type in ('Swim', 'OpenWaterSwim')
             and ga.activity_type in ('swimming', 'open_water_swimming')         then 0
            when sa.activity_type in ('Kayaking', 'Canoe')
             and ga.activity_type = 'whitewater_rafting_kayaking'                then 0
            when sa.activity_type = 'Golf'
             and ga.activity_type = 'golf'                                       then 0
            else 1
        end                                         as type_mismatch
    from strava as sa
    left join garmin_activity_raw as ga
        on cast(ga.start_time_local as date)
               between (sa.activity_date - 1) and (sa.activity_date + 1)
),

-- Rank candidates: same day > type match > closest start time
garmin_activity_ranked as (
    select *,
        row_number() over (
            partition by strava_activity_id
            order by date_diff_days, type_mismatch, start_diff_s
        ) as match_rank
    from garmin_activity_candidates
),

garmin_activity as (
    select * from garmin_activity_ranked
    where match_rank = 1
),

joined as (
    select
        -- ── activity identity ──────────────────────────────────────────────────
        sa.activity_id,
        ga.garmin_activity_id,
        sa.activity_date,
        sa.started_at,
        sa.activity_name,
        sa.activity_type,
        sa.from_upload,

        -- ── join quality flags ─────────────────────────────────────────────────
        -- Activity starting after 22:00 local: UTC date may differ from local date,
        -- which means the same-day readiness join could be off by one day.
        hour(sa.started_at) >= 22                    as late_start_utc_risk,
        ga.garmin_activity_id is not null            as garmin_activity_matched,
        ga.type_mismatch = 0                         as garmin_match_type_compatible,
        ga.start_diff_s                              as garmin_match_start_diff_s,

        -- ── performance: distance & speed (Strava) ────────────────────────────
        sa.distance_m,
        sa.distance_m / 1000.0                      as distance_km,
        sa.elapsed_time_s,
        sa.moving_time_s,
        sa.average_speed_ms,
        sa.average_speed_ms * 3.6                   as average_speed_kph,
        sa.max_speed_ms,

        -- ── performance: elevation (Strava) ───────────────────────────────────
        sa.elevation_gain_m,
        sa.elevation_loss_m,
        sa.elevation_low_m,
        sa.elevation_high_m,
        sa.max_grade_pct,
        sa.average_grade_pct,
        sa.grade_adjusted_distance_m,
        sa.average_grade_adjusted_pace,

        -- ── performance: heart rate (Strava) ──────────────────────────────────
        sa.average_heart_rate_bpm,
        sa.max_heart_rate_bpm,

        -- ── performance: power (Strava — speed/gradient model, NOT power meter) ─
        sa.average_watts,
        sa.weighted_average_power_w,
        sa.total_work_kj,
        sa.power_count,

        -- ── performance: power (Garmin — power meter activities only, ~7%) ─────
        ga.garmin_avg_power_w,
        ga.garmin_norm_power_w,

        -- ── performance: cadence ──────────────────────────────────────────────
        sa.average_cadence,
        sa.max_cadence,

        -- ── performance: effort ───────────────────────────────────────────────
        sa.calories_kcal,
        sa.relative_effort,
        sa.perceived_exertion,
        sa.perceived_relative_effort,

        -- ── performance: activity-specific ────────────────────────────────────
        sa.total_steps,

        -- ── training load & effect (Garmin activity-level, if matched) ─────────
        ga.aerobic_training_effect,
        ga.anaerobic_training_effect,
        ga.training_effect_label,
        ga.activity_training_load,
        ga.body_battery_change          as activity_body_battery_change,
        ga.is_pr,

        -- ── HR zone time (Garmin activity-level, if matched) ──────────────────
        ga.hr_zone_0_s,
        ga.hr_zone_1_s,
        ga.hr_zone_2_s,
        ga.hr_zone_3_s,
        ga.hr_zone_4_s,
        ga.hr_zone_5_s,
        ga.hr_zone_6_s,

        -- ── same-day readiness context (Garmin daily spine) ───────────────────
        gd.readiness_score,
        gd.readiness_level,
        gd.readiness_feedback_short,

        gd.hrv_factor_pct,
        gd.hrv_factor_feedback,
        gd.readiness_hrv_weekly_avg_ms,

        gd.sleep_score_factor_pct,
        gd.sleep_score_factor_feedback,
        gd.sleep_history_factor_pct,
        gd.sleep_history_factor_feedback,

        gd.recovery_time_h,
        gd.recovery_time_factor_pct,
        gd.recovery_time_factor_feedback,

        gd.acwr_factor_pct,
        gd.acwr_factor_feedback,
        gd.readiness_acute_load,

        gd.stress_history_factor_pct,
        gd.stress_history_factor_feedback,

        gd.valid_sleep,

        -- ── same-day sleep ────────────────────────────────────────────────────
        gd.sleep_score,
        gd.total_sleep_s,
        gd.deep_sleep_s,
        gd.rem_sleep_s,
        gd.light_sleep_s,
        gd.sleep_awake_s,
        gd.avg_sleep_stress,

        -- ── same-day body battery & stress ────────────────────────────────────
        gd.body_battery_start_of_day,
        gd.body_battery_highest,
        gd.stress_avg,
        gd.stress_avg_awake,

        -- ── same-day HRV & resting HR (health_status, Sep 2025+) ──────────────
        gd.hrv_ms,
        gd.hrv_status,
        gd.health_status_resting_hr_bpm,

        -- ── same-day training load (Garmin daily) ─────────────────────────────
        gd.acute_load_7d,
        gd.chronic_load_28d,
        gd.acwr,
        gd.acwr_status,

        -- ── same-day training status ──────────────────────────────────────────
        gd.training_status,
        gd.fitness_level_trend,

        -- ── weather at time of activity (Strava) ──────────────────────────────
        sa.average_temperature_c,
        sa.weather_temperature_c,
        sa.apparent_temperature_c,
        sa.dewpoint_c,
        sa.humidity_fraction,
        sa.wind_speed_ms,
        sa.wind_gust_ms,
        sa.wind_bearing_deg,
        sa.weather_pressure_hpa,
        sa.precipitation_intensity,
        sa.precipitation_probability,
        sa.cloud_cover_fraction,
        sa.uv_index,

        -- ── misc ───────────────────────────────────────────────────────────────
        sa.activity_gear,
        sa.commute,
        sa.athlete_weight_kg,
        sa.bike_weight_kg

    from strava as sa
    left join garmin_daily  as gd on gd.calendar_date = sa.activity_date
    left join garmin_activity as ga on ga.strava_activity_id = sa.activity_id
)

select * from joined
