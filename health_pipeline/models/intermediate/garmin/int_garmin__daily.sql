-- int_garmin__daily
-- One row per calendar day — the readiness spine.
-- Joins all day-grain Garmin staging models on calendar_date.
--
-- Coverage by source (approximate, single-athlete):
--   stg_garmin__daily_summary      Apr 2020 – present   (longest history)
--   stg_garmin__sleep              Apr 2020 – present
--   stg_garmin__training_load      ~2022 – present      (needs 28-day window to start)
--   stg_garmin__training_status    ~2022 – present
--   stg_garmin__training_readiness Dec 2023 – present
--   stg_garmin__health_status      Sep 2025 – present   (shortest history)
--
-- Join strategy: LEFT JOIN everything onto the daily_summary spine.
-- Rows before a source's start date will have NULLs for its columns.
-- This preserves the full date range for activity-side joins downstream.

with daily_summary as (
    select * from {{ ref('stg_garmin__daily_summary') }}
),

sleep as (
    select * from {{ ref('stg_garmin__sleep') }}
),

training_load as (
    select * from {{ ref('stg_garmin__training_load') }}
),

training_status as (
    select * from {{ ref('stg_garmin__training_status') }}
),

training_readiness as (
    select * from {{ ref('stg_garmin__training_readiness') }}
),

health_status as (
    select * from {{ ref('stg_garmin__health_status') }}
),

joined as (
    select
        -- ── spine ─────────────────────────────────────────────────────────────
        ds.calendar_date,
        ds.user_profile_pk,

        -- ── daily wellness summary ─────────────────────────────────────────────
        ds.total_steps,
        ds.daily_step_goal,
        ds.total_distance_m,

        ds.total_kcal,
        ds.active_kcal,
        ds.bmr_kcal,

        ds.highly_active_s,
        ds.active_s,
        ds.moderate_intensity_min_week_to_date,
        ds.vigorous_intensity_min_week_to_date,
        ds.is_vigorous_day,

        ds.min_hr_bpm,
        ds.max_hr_bpm,
        ds.resting_hr_bpm                   as resting_hr_7d_avg_bpm,   -- 7-day rolling avg
        ds.current_resting_hr_bpm,                                       -- same-day

        ds.stress_avg,
        ds.stress_max,
        ds.stress_avg_awake,
        ds.stress_duration_s,

        ds.body_battery_charged,
        ds.body_battery_drained,
        ds.body_battery_highest,
        ds.body_battery_lowest,
        ds.body_battery_start_of_day,
        ds.body_battery_end_of_day,
        ds.body_battery_sleep_start,
        ds.body_battery_sleep_end,
        ds.body_battery_gained_during_sleep,

        ds.avg_waking_respiration_brpm,
        ds.avg_altitude_m,
        ds.floors_ascended_m,

        -- ── sleep ──────────────────────────────────────────────────────────────
        sl.sleep_start_utc,
        sl.sleep_end_utc,
        sl.sleep_window_confirmation_type,
        sl.total_sleep_s,
        sl.deep_sleep_s,
        sl.light_sleep_s,
        sl.rem_sleep_s,
        sl.awake_s                          as sleep_awake_s,
        sl.awake_count,
        sl.avg_sleep_stress,
        sl.restless_moment_count,
        sl.avg_respiration_brpm             as sleep_avg_respiration_brpm,
        sl.sleep_score,
        sl.sleep_score_quality,
        sl.sleep_score_duration,
        sl.sleep_score_recovery,
        sl.sleep_score_deep,
        sl.sleep_score_rem,
        sl.sleep_score_restfulness,
        sl.sleep_score_feedback,

        -- ── training load (ACWR spine) ─────────────────────────────────────────
        tl.acute_load_7d,
        tl.chronic_load_28d,
        tl.acwr,
        tl.acwr_pct,
        tl.acwr_status,
        tl.acwr_status_feedback,

        -- ── training status ────────────────────────────────────────────────────
        ts.training_status,
        ts.fitness_level_trend,
        ts.feedback_phrase              as training_status_feedback,

        -- ── training readiness ────────────────────────────────────────────────
        tr.readiness_score,
        tr.readiness_level,
        tr.feedback_short               as readiness_feedback_short,
        tr.feedback_long                as readiness_feedback_long,

        tr.hrv_weekly_avg_ms            as readiness_hrv_weekly_avg_ms,
        tr.hrv_factor_pct,
        tr.hrv_factor_feedback,

        tr.sleep_score_factor_pct,
        tr.sleep_score_factor_feedback,
        tr.sleep_history_factor_pct,
        tr.sleep_history_factor_feedback,

        tr.recovery_time_h,
        tr.recovery_time_factor_pct,
        tr.recovery_time_factor_feedback,

        tr.acute_load                   as readiness_acute_load,
        tr.acwr_factor_pct,
        tr.acwr_factor_feedback,

        tr.stress_history_factor_pct,
        tr.stress_history_factor_feedback,

        tr.valid_sleep,
        tr.input_context                as readiness_input_context,
        tr.assessed_at_local            as readiness_assessed_at_local,

        -- ── health status (HRV / resting HR / skin temp / respiration) ────────
        -- Available Sep 2025+; NULLs before that date are expected
        hs.hrv_ms,
        hs.hrv_baseline_lower_ms,
        hs.hrv_baseline_upper_ms,
        hs.hrv_status,
        hs.hrv_pct_in_range,

        hs.resting_hr_bpm               as health_status_resting_hr_bpm,
        hs.resting_hr_baseline_lower,
        hs.resting_hr_baseline_upper,
        hs.resting_hr_status,
        hs.resting_hr_pct_in_range,

        hs.skin_temp_delta_c,
        hs.skin_temp_status,

        hs.respiration_brpm             as health_status_respiration_brpm,
        hs.respiration_status,

        hs.is_onboarding                as health_status_is_onboarding

    from daily_summary as ds
    left join sleep           as sl on sl.calendar_date = ds.calendar_date
    left join training_load   as tl on tl.calendar_date = ds.calendar_date
    left join training_status as ts on ts.calendar_date = ds.calendar_date
    left join training_readiness as tr on tr.calendar_date = ds.calendar_date
    left join health_status   as hs on hs.calendar_date = ds.calendar_date
)

select * from joined
