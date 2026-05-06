-- stg_garmin__health_status
-- One row per calendar day — pivots the long-format metrics table (5 rows/day)
-- to a wide format with one column per metric type.
-- Key transforms:
--   - Pivot HRV, HR, SKIN_TEMP_C, RESPIRATION from long to wide
--   - SPO2 excluded (always UNKNOWN for this device configuration)
--   - Filter: drop UNKNOWN status rows (device setup day, 2025-09-17)
--   - The ONBOARDING rows (~first week) are KEPT with a flag so downstream
--     models can choose to exclude them; baseline limits are zero during this period

with source as (
    select * from {{ source('garmin', 'garmin__health_status') }}
),

-- Exclude the setup day where all values are 0.0 / UNKNOWN
active as (
    select * from source
    where status != 'UNKNOWN'
),

pivoted as (
    select
        calendar_date,
        -- Capture whether this date is still in the ONBOARDING period
        -- (any metric still onboarding means the day is in calibration)
        max(case when status = 'ONBOARDING' then 1 else 0 end) = 1
            as is_onboarding,

        -- ── HRV (rMSSD, milliseconds) ─────────────────────────────────────────
        max(case when metric_type = 'HRV' then cast(value as double) end)
            as hrv_ms,
        max(case when metric_type = 'HRV' then cast(baseline_upper_limit as double) end)
            as hrv_baseline_upper_ms,
        max(case when metric_type = 'HRV' then cast(baseline_lower_limit as double) end)
            as hrv_baseline_lower_ms,
        max(case when metric_type = 'HRV' then status end)
            as hrv_status,
        max(case when metric_type = 'HRV' then cast(percentage as double) end)
            as hrv_pct_in_range,

        -- ── Resting heart rate (bpm) ──────────────────────────────────────────
        max(case when metric_type = 'HR' then cast(value as double) end)
            as resting_hr_bpm,
        max(case when metric_type = 'HR' then cast(baseline_upper_limit as double) end)
            as resting_hr_baseline_upper,
        max(case when metric_type = 'HR' then cast(baseline_lower_limit as double) end)
            as resting_hr_baseline_lower,
        max(case when metric_type = 'HR' then status end)
            as resting_hr_status,
        max(case when metric_type = 'HR' then cast(percentage as double) end)
            as resting_hr_pct_in_range,

        -- ── Skin temperature delta (°C from personal baseline) ────────────────
        max(case when metric_type = 'SKIN_TEMP_C' then cast(value as double) end)
            as skin_temp_delta_c,
        max(case when metric_type = 'SKIN_TEMP_C' then cast(baseline_upper_limit as double) end)
            as skin_temp_baseline_upper,
        max(case when metric_type = 'SKIN_TEMP_C' then cast(baseline_lower_limit as double) end)
            as skin_temp_baseline_lower,
        max(case when metric_type = 'SKIN_TEMP_C' then status end)
            as skin_temp_status,

        -- ── Respiration rate (br/min) ─────────────────────────────────────────
        max(case when metric_type = 'RESPIRATION' then cast(value as double) end)
            as respiration_brpm,
        max(case when metric_type = 'RESPIRATION' then cast(baseline_upper_limit as double) end)
            as respiration_baseline_upper,
        max(case when metric_type = 'RESPIRATION' then cast(baseline_lower_limit as double) end)
            as respiration_baseline_lower,
        max(case when metric_type = 'RESPIRATION' then status end)
            as respiration_status,

        -- ── Day-level metadata ─────────────────────────────────────────────────
        max(cast(outliers_count as integer))    as outliers_count,
        max(cast(create_timestamp_utc as timestamp)) as created_at_utc

    from active
    group by calendar_date
)

select
    cast(calendar_date as date) as calendar_date,
    is_onboarding,
    hrv_ms,
    hrv_baseline_upper_ms,
    hrv_baseline_lower_ms,
    hrv_status,
    hrv_pct_in_range,
    resting_hr_bpm,
    resting_hr_baseline_upper,
    resting_hr_baseline_lower,
    resting_hr_status,
    resting_hr_pct_in_range,
    skin_temp_delta_c,
    skin_temp_baseline_upper,
    skin_temp_baseline_lower,
    skin_temp_status,
    respiration_brpm,
    respiration_baseline_upper,
    respiration_baseline_lower,
    respiration_status,
    outliers_count,
    created_at_utc
from pivoted
