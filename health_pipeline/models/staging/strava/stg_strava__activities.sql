-- stg_strava__activities
-- One row per Strava activity (ride, run, hike, strength, ski, etc.).
-- Key transforms:
--   - started_at and activity_date already parsed by ingest.py
--   - Casts booleans (stored as object by pandas) to bool
--   - Exposes elapsed_time / distance / max_heart_rate / relative_effort / commute
--     from the detailed (second-occurrence) columns; summary variants dropped

with source as (
    select * from {{ source('strava', 'strava__activities') }}
),

renamed as (
    select
        -- ── keys ──────────────────────────────────────────────────────────────
        cast(activity_id as bigint)             as activity_id,

        -- ── timestamps ────────────────────────────────────────────────────────
        -- Both columns already populated by ingest.py via pandas to_datetime
        cast(started_at as timestamp)           as started_at,  -- local time, no UTC offset
        cast(activity_date as date)             as activity_date,

        -- ── activity metadata ─────────────────────────────────────────────────
        activity_name,
        activity_type,
        activity_description,
        activity_gear,
        filename,
        cast(from_upload as boolean)            as from_upload,

        -- ── timing (detailed stream) ──────────────────────────────────────────
        cast(elapsed_time as integer)           as elapsed_time_s,
        cast(moving_time as integer)            as moving_time_s,

        -- ── distance & speed (detailed stream) ───────────────────────────────
        cast(distance as double)                as distance_m,
        cast(average_speed as double)           as average_speed_ms,
        cast(max_speed as double)               as max_speed_ms,
        cast(grade_adjusted_distance as double) as grade_adjusted_distance_m,

        -- ── elevation ─────────────────────────────────────────────────────────
        cast(elevation_gain as double)          as elevation_gain_m,
        cast(elevation_loss as double)          as elevation_loss_m,
        cast(elevation_low as double)           as elevation_low_m,
        cast(elevation_high as double)          as elevation_high_m,

        -- ── grade ─────────────────────────────────────────────────────────────
        cast(max_grade as double)               as max_grade_pct,
        cast(average_grade as double)           as average_grade_pct,
        cast(average_grade_adjusted_pace as double) as average_grade_adjusted_pace,

        -- ── heart rate ────────────────────────────────────────────────────────
        cast(average_heart_rate as integer)     as average_heart_rate_bpm,
        cast(max_heart_rate as integer)         as max_heart_rate_bpm,  -- detailed stream

        -- ── cadence ───────────────────────────────────────────────────────────
        cast(average_cadence as integer)        as average_cadence,
        cast(max_cadence as integer)            as max_cadence,

        -- ── power (Strava-estimated for rides; NOT raw power meter data) ──────
        cast(average_watts as double)           as average_watts,
        cast(weighted_average_power as double)  as weighted_average_power_w,
        cast(power_count as integer)            as power_count,
        cast(total_work as double)              as total_work_kj,

        -- ── effort ────────────────────────────────────────────────────────────
        cast(calories as integer)               as calories_kcal,
        cast(relative_effort as double)         as relative_effort,  -- detailed stream
        cast(perceived_exertion as integer)     as perceived_exertion,
        cast(perceived_relative_effort as integer) as perceived_relative_effort,
        cast(prefer_perceived_exertion as boolean) as prefer_perceived_exertion,

        -- ── activity-specific ─────────────────────────────────────────────────
        cast(total_steps as integer)            as total_steps,
        cast(average_temperature as double)     as average_temperature_c,
        cast(number_of_runs as integer)         as number_of_runs,
        cast(total_cycles as integer)           as total_cycles,

        -- ── athlete profile at time of activity ───────────────────────────────
        cast(athlete_weight as double)          as athlete_weight_kg,
        cast(bike_weight as double)             as bike_weight_kg,

        -- ── gear ──────────────────────────────────────────────────────────────
        cast(bike as integer)                   as bike_id,

        -- ── weather ───────────────────────────────────────────────────────────
        cast(weather_observation_time as bigint) as weather_observation_time,
        cast(weather_condition as integer)      as weather_condition,
        cast(weather_temperature as double)     as weather_temperature_c,
        cast(apparent_temperature as double)    as apparent_temperature_c,
        cast(dewpoint as double)                as dewpoint_c,
        cast(humidity as double)                as humidity_fraction,
        cast(weather_pressure as double)        as weather_pressure_hpa,
        cast(wind_speed as double)              as wind_speed_ms,
        cast(wind_gust as double)               as wind_gust_ms,
        cast(wind_bearing as integer)           as wind_bearing_deg,
        cast(precipitation_intensity as double) as precipitation_intensity,
        cast(precipitation_probability as double) as precipitation_probability,
        cast(precipitation_type as integer)     as precipitation_type,
        cast(cloud_cover as double)             as cloud_cover_fraction,
        cast(weather_visibility as double)      as weather_visibility_m,
        cast(uv_index as double)                as uv_index,
        cast(weather_ozone as double)           as weather_ozone_du,
        cast(sunrise_time as bigint)            as sunrise_time,
        cast(sunset_time as bigint)             as sunset_time,
        cast(moon_phase as double)              as moon_phase,

        -- ── MTB-specific ──────────────────────────────────────────────────────
        cast(total_grit as double)              as total_grit,
        cast(average_flow as double)            as average_flow,
        cast(dirt_distance as double)           as dirt_distance_m,

        -- ── misc flags ────────────────────────────────────────────────────────
        cast(commute as boolean)                as commute,  -- detailed stream
        cast(flagged as integer)                as flagged,
        cast(average_elapsed_speed as double)   as average_elapsed_speed_ms,
        cast(training_load as integer)          as strava_training_load,
        cast(intensity as integer)              as strava_intensity,
        cast(recovery as integer)               as strava_recovery,
        media

    from source
)

select * from renamed
