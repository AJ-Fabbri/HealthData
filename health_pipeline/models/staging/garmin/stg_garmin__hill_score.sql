-- stg_garmin__hill_score
-- One row per calendar day — Garmin Hill Score (climbing ability composite).
-- Key transforms:
--   - calendar_date and timestamp are Unix epoch milliseconds → convert
--   - Deduplicate: keep latest per calendar_date

with source as (
    select * from {{ source('garmin', 'garmin__hill_score') }}
),

converted as (
    select *,
        cast(to_timestamp(cast(calendar_date as bigint) / 1000.0) as date) as calendar_date_d,
        to_timestamp(cast(timestamp as bigint) / 1000.0)                   as assessed_at_utc
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

        cast(overall_score as integer)                 as hill_score,
        cast(strength_score as integer)                as hill_score_strength,
        cast(endurance_score as integer)               as hill_score_endurance,
        cast(hill_score_classification_id as integer)  as classification_id,
        cast(hill_score_feedback_phrase_id as integer) as feedback_phrase_id

    from deduped
    where rn = 1
)

select * from renamed
