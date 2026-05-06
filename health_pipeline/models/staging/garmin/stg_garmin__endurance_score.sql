-- stg_garmin__endurance_score
-- One row per calendar day — Garmin Endurance Score (0–10,000+).
-- Measures accumulated aerobic capacity weighted by duration and intensity.
-- Key transforms:
--   - calendar_date_ms is Unix epoch milliseconds → convert to date
--   - Deduplicate: keep latest per calendar_date
--   - Per-sport contributions already extracted to columns by ingest.py

with source as (
    select * from {{ source('garmin', 'garmin__endurance_score') }}
),

converted as (
    select *,
        cast(to_timestamp(cast(calendar_date_ms as bigint) / 1000.0) as date) as calendar_date_d,
        to_timestamp(cast(timestamp_ms as bigint) / 1000.0)                   as assessed_at_utc
    from source
),

deduped as (
    select *,
        row_number() over (
            partition by calendar_date_d
            order by assessed_at_utc desc
        ) as rn
    from converted
),

renamed as (
    select
        calendar_date_d                                 as calendar_date,
        cast(user_profile_pk as integer)               as user_profile_pk,
        cast(device_id as bigint)                      as device_id,
        assessed_at_utc,
        cast(primary_training_device as boolean)       as is_primary_device,

        -- ── overall endurance score ───────────────────────────────────────────
        cast(overall_score as integer)                 as endurance_score,
        cast(classification as integer)                as classification_id,
        cast(feedback_phrase as integer)               as feedback_phrase_id,

        -- ── per-sport contributions (%) ────────────────────────────────────────
        -- sport groups: 0=cycling, 1=running, 3=hiking/walking, 8=other aerobic
        cast(cycling_contribution as double)           as cycling_contribution_pct,
        cast(running_contribution as double)           as running_contribution_pct,
        cast(hiking_walking_contribution as double)    as hiking_walking_contribution_pct,
        cast(other_aerobic_contribution as double)     as other_aerobic_contribution_pct

    from deduped
    where rn = 1
)

select * from renamed
