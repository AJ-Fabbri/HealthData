#!/usr/bin/env python3
"""
Generate a synthetic health & fitness dataset for demo purposes.

Creates a year of plausible Strava activities + Garmin daily health metrics
with realistic distributions and correlations. All dates are offset to recent
history, so users see "current" demo data.

Run from repo root:
    python scripts/generate_sample_data.py

Output: data/healthdata_synthetic.duckdb
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "healthdata_synthetic.duckdb"


# Seed for reproducibility while keeping variation
SEED = 42
random.seed(SEED)
np.random.seed(SEED)


def date_range(start: datetime, days: int):
    """Generate a sequence of dates."""
    return [start + timedelta(days=i) for i in range(days)]


def generate_strava_activities(start_date: datetime, num_days: int = 365) -> pd.DataFrame:
    """
    Generate ~200-250 activities spread across a year (3-4 per week).
    Realistic mix: cycling (50%), running (35%), hiking/climbing (15%).
    """
    activities = []
    activity_id = 10000

    # ~3.5 activities per week on average
    activity_probability = 0.5
    activity_types = {
        "Ride": 0.45,
        "Run": 0.35,
        "Hike": 0.12,
        "Alpine Ski": 0.05,
        "Walk": 0.03,
    }

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)

        # Cluster activities: rest days followed by activity bursts
        day_of_week = current_date.weekday()
        if day_of_week == 6:  # Sunday: lighter activity
            activity_probability = 0.3
        elif day_of_week == 0:  # Monday: often rest
            activity_probability = 0.2
        else:
            activity_probability = 0.5

        if random.random() > activity_probability:
            continue

        activity_type = random.choices(
            list(activity_types.keys()),
            weights=list(activity_types.values()),
        )[0]

        # Generate realistic metrics by type
        if activity_type == "Ride":
            distance = np.clip(np.random.normal(40, 12), 8, 100)  # 40 km ± 12, clipped
            elapsed_time = distance / np.clip(np.random.normal(22, 3), 15, 30)  # 15-30 km/h
            elevation = np.clip(np.random.normal(300, 150), 0, 1500)
            avg_hr = np.clip(np.random.normal(135, 12), 100, 170)

        elif activity_type == "Run":
            distance = np.clip(np.random.normal(10, 2.5), 3, 20)  # 10 km ± 2.5
            pace_min_per_km = np.clip(np.random.normal(5.5, 0.6), 4, 8)  # 4-8 min/km
            elapsed_time = distance * pace_min_per_km / 60.0  # convert to hours
            elevation = np.clip(np.random.normal(100, 70), 0, 500)
            avg_hr = np.clip(np.random.normal(155, 10), 130, 180)

        elif activity_type == "Hike":
            distance = np.clip(np.random.normal(12, 3), 3, 25)
            elapsed_time_min = np.clip(distance / 3.5 * 60 + np.random.normal(0, 10), 30, 480)  # 30min-8h in minutes
            elapsed_time = elapsed_time_min / 60.0  # convert to hours
            elevation = np.clip(np.random.normal(400, 150), 50, 1500)
            avg_hr = np.clip(np.random.normal(120, 15), 90, 160)

        elif activity_type == "Alpine Ski":
            distance = np.clip(np.random.normal(30, 8), 10, 80)
            elapsed_time = np.clip(np.random.normal(180, 30), 60, 360) / 60.0  # convert minutes to hours
            elevation = np.clip(np.random.normal(2000, 400), 500, 3500)
            avg_hr = np.clip(np.random.normal(130, 20), 100, 180)

        else:  # Walk
            distance = np.clip(np.random.normal(5, 1.5), 1.5, 15)
            pace_kmh = np.clip(np.random.normal(4.5, 0.5), 3, 6)
            elapsed_time = distance / pace_kmh  # already in hours
            elevation = np.clip(np.random.normal(50, 40), 0, 300)
            avg_hr = np.clip(np.random.normal(100, 10), 70, 140)

        max_hr = np.clip(avg_hr + np.random.normal(25, 5), avg_hr, 200)

        activities.append({
            "activity_id": activity_id,
            "activity_name": f"{activity_type} on {current_date.strftime('%a')}",
            "activity_description": f"Demo {activity_type.lower()}",
            "activity_type": activity_type,
            "activity_date": current_date.date(),
            "activity_date_str": current_date.strftime("%b %d, %Y, %I:%M:%S %p"),
            "started_at": current_date,
            "elapsed_time": max(0.25, elapsed_time),  # min 15 minutes
            "distance": max(0.1, distance),
            "distance_summary": max(0.1, distance),
            "elevation_gain": max(0, elevation),
            "average_heartrate": max(60, avg_hr),
            "max_heart_rate": max(avg_hr, max_hr),
            "max_heart_rate_summary": max(avg_hr, max_hr),
            "perceived_exertion": np.random.randint(4, 10),
        })
        activity_id += 1

    return pd.DataFrame(activities)


def generate_garmin_daily_summary(
    start_date: datetime, num_days: int = 365
) -> pd.DataFrame:
    """
    Generate one row per calendar day: steps, calories, stress, body battery, sleep prep.
    """
    rows = []

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)

        # Steps: weekday ~12k, weekend ~8k with variation
        base_steps = 12000 if current_date.weekday() < 5 else 8000
        total_steps = max(2000, int(np.random.normal(base_steps, 3000)))

        # Activity minutes: correlated with step count and day of week
        if total_steps > 15000:
            activity_min = int(np.random.normal(60, 15))
        else:
            activity_min = int(np.random.normal(30, 10))

        # Body battery: 0-100, influenced by prior activity
        body_battery_start = int(np.random.normal(70, 15))
        body_battery_start = np.clip(body_battery_start, 5, 100)
        body_battery_end = int(np.random.normal(50, 20))
        body_battery_end = np.clip(body_battery_end, 10, 100)

        # Stress: inverse of body battery
        stress_avg = 100 - np.random.normal(body_battery_end / 1.5, 10)
        stress_avg = np.clip(stress_avg, 10, 80)

        # Calories: depends on activity
        total_kcal = 1800 + activity_min * 7 + np.random.normal(0, 150)
        remaining_kcal = 2500 - total_kcal  # Daily calorie goal - consumed

        rows.append({
            "user_profile_pk": 1,
            "calendar_date": current_date.date(),
            "uuid": f"day-{day_offset}",
            "wellness_start_time_gmt": f"{current_date.isoformat()}T00:00:00Z",
            "wellness_end_time_gmt": (current_date + timedelta(days=1)).isoformat() + "T00:00:00Z",
            "wellness_start_time_local": f"{current_date.isoformat()}T00:00:00",
            "wellness_end_time_local": (current_date + timedelta(days=1)).isoformat() + "T00:00:00",
            "total_steps": max(0, total_steps),
            "daily_step_goal": 10000,
            "total_distance_meters": total_steps * 0.76,  # avg stride ~0.76m
            "wellness_distance_meters": total_steps * 0.76 * 0.3,  # portion during wellness
            "total_kilocalories": max(1500, total_kcal),
            "active_kilocalories": max(100, activity_min * 7),
            "bmr_kilocalories": 1800,
            "remaining_kilocalories": max(0, remaining_kcal),
            "highly_active_seconds": activity_min * 60,
            "active_seconds": activity_min * 120,
            "moderate_intensity_minutes": int(activity_min * 0.6),
            "vigorous_intensity_minutes": int(activity_min * 0.4),
            "is_vigorous_day": activity_min > 40,
            "min_heart_rate": np.random.randint(45, 60),
            "max_heart_rate": np.random.randint(140, 180),
            "resting_heart_rate": int(np.random.normal(52, 3)),
            "current_day_resting_heart_rate": int(np.random.normal(52, 3)),
            "stress_avg_total": int(stress_avg),
            "stress_max_total": int(stress_avg + 20),
            "stress_duration_total_s": int(stress_avg * 30),
            "stress_avg_awake": int(stress_avg),
            "body_battery_charged": int(np.random.normal(20, 5)),
            "body_battery_drained": int(np.random.normal(35, 8)),
            "body_battery_highest": 100,
            "body_battery_lowest": int(np.random.normal(30, 10)),
            "body_battery_start_of_day": body_battery_start,
            "body_battery_end_of_day": body_battery_end,
        })

    return pd.DataFrame(rows)


def generate_garmin_sleep(start_date: datetime, num_days: int = 365) -> pd.DataFrame:
    """
    Generate sleep data: 6-8 hours, realistic stage breakdown.
    """
    rows = []

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)

        # Most nights 7 ± 1.5 hours, occasional short/long nights
        total_sleep_hours = np.random.normal(7, 1.5)
        total_sleep_hours = np.clip(total_sleep_hours, 3, 10)

        total_seconds = int(total_sleep_hours * 3600)
        sleep_start = current_date + timedelta(hours=23)
        sleep_end = sleep_start + timedelta(seconds=total_seconds)

        # Sleep stages (realistic proportions)
        deep_pct = np.random.normal(0.13, 0.04)  # 13% ± 4%
        light_pct = np.random.normal(0.50, 0.06)
        rem_pct = np.random.normal(0.20, 0.05)
        awake_pct = 1 - deep_pct - light_pct - rem_pct
        awake_pct = np.clip(awake_pct, 0.05, 0.15)

        deep_s = int(total_seconds * deep_pct)
        light_s = int(total_seconds * light_pct)
        rem_s = int(total_seconds * rem_pct)
        awake_s = total_seconds - deep_s - light_s - rem_s

        # Sleep score: 70-90 typical, influenced by sleep duration
        if 6 < total_sleep_hours < 8:
            sleep_score = int(np.random.normal(82, 8))
        elif total_sleep_hours < 6:
            sleep_score = int(np.random.normal(65, 10))
        else:
            sleep_score = int(np.random.normal(78, 8))

        sleep_score = np.clip(sleep_score, 20, 100)

        rows.append({
            "calendar_date": current_date.date(),
            "sleep_start_timestamp_gmt": sleep_start.isoformat() + "Z",
            "sleep_end_timestamp_gmt": sleep_end.isoformat() + "Z",
            "sleep_window_confirmation_type": "CONFIRMED",
            "retro": False,
            "deep_sleep_seconds": max(0, deep_s),
            "light_sleep_seconds": max(0, light_s),
            "rem_sleep_seconds": max(0, rem_s),
            "awake_sleep_seconds": max(0, awake_s),
            "unmeasurable_seconds": 0,
            "average_respiration": int(np.random.normal(15, 1)),
            "lowest_respiration": int(np.random.normal(12, 1)),
            "highest_respiration": int(np.random.normal(18, 1)),
            "awake_count": int(np.random.normal(3, 1.5)),
            "restless_moment_count": int(np.random.normal(2, 1)),
            "sleep_score_overall": sleep_score,
            "sleep_score_quality": int(np.random.normal(sleep_score * 0.95, 5)),
            "sleep_score_duration": int(np.random.normal(sleep_score * 0.9, 8)),
            "sleep_score_recovery": int(np.random.normal(sleep_score * 0.88, 6)),
            "sleep_score_deep": int(np.random.normal(sleep_score * 0.85, 8)),
            "sleep_score_rem": int(np.random.normal(sleep_score * 0.85, 7)),
        })

    return pd.DataFrame(rows)


def generate_garmin_health_status(start_date: datetime, num_days: int = 365) -> pd.DataFrame:
    """
    Generate HRV and resting HR daily metrics in long format.
    Each day: 2 rows (HRV + resting HR).
    """
    rows = []

    # HRV baseline + variation
    hrv_baseline = 65

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)

        # HRV: varies with recovery; baseline ~65 ms with ±20 variation
        hrv = int(np.random.normal(hrv_baseline, 15))
        hrv = np.clip(hrv, 20, 120)

        # Interpret as HRV status based on athlete baseline
        if hrv > 80:
            hrv_status = "VERY_GOOD"
        elif hrv > 65:
            hrv_status = "GOOD"
        elif hrv > 50:
            hrv_status = "BALANCED"
        else:
            hrv_status = "POOR"

        rows.append({
            "calendar_date": current_date.date(),
            "create_timestamp_utc": current_date.isoformat() + "Z",
            "outliers_count": 0,
            "metric_type": "HRV",
            "value": hrv,
            "baseline_upper_limit": 100,
            "baseline_lower_limit": 30,
            "status": hrv_status,
            "percentage": int((hrv / 100) * 100),
        })

        # Resting HR: 50-65 bpm typical
        rhr = int(np.random.normal(52, 3))
        rhr = np.clip(rhr, 45, 75)

        rows.append({
            "calendar_date": current_date.date(),
            "create_timestamp_utc": current_date.isoformat() + "Z",
            "outliers_count": 0,
            "metric_type": "RESTING_HR",
            "value": rhr,
            "baseline_upper_limit": 75,
            "baseline_lower_limit": 40,
            "status": "NORMAL" if 45 <= rhr <= 65 else "ABNORMAL",
            "percentage": int((rhr / 75) * 100),
        })

    return pd.DataFrame(rows)


def generate_garmin_training_readiness(
    start_date: datetime, num_days: int = 365
) -> pd.DataFrame:
    """
    Generate training readiness scores (0-100).
    Influenced by prior activity and recovery.
    """
    rows = []

    readiness_score = 50
    activity_level = 0

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)

        # Readiness: recovers slowly after hard days, boosts with rest
        if activity_level > 50:
            readiness_score -= np.random.normal(8, 3)
        else:
            readiness_score += np.random.normal(5, 2)

        readiness_score = np.clip(readiness_score, 15, 95)

        # Status classification
        if readiness_score > 70:
            status = "READY"
        elif readiness_score > 55:
            status = "BALANCED"
        else:
            status = "NEED_RECOVERY"

        rows.append({
            "user_profile_pk": 1,
            "calendar_date": current_date.date(),
            "timestamp": int(current_date.timestamp() * 1000),
            "training_readiness_score": int(readiness_score),
            "status": status,
            "recovery_window_days": 1 if status == "NEED_RECOVERY" else 0,
        })

        # Decay activity level
        activity_level = max(0, activity_level - np.random.normal(10, 5))

    return pd.DataFrame(rows)


def main() -> None:
    print(f"Generating synthetic dataset: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    # Generate data for the past year, ending today
    today = datetime.now().date()
    start_date = datetime(today.year - 1, today.month, today.day, 6, 0, 0)

    print("  - Generating Strava activities...")
    strava = generate_strava_activities(start_date, num_days=365)
    con.execute("CREATE OR REPLACE TABLE raw.strava__activities AS SELECT * FROM strava")
    print(f"    {len(strava):,} activities")

    print("  - Generating Garmin daily summaries...")
    daily = generate_garmin_daily_summary(start_date, num_days=365)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__daily_summary AS SELECT * FROM daily")
    print(f"    {len(daily):,} days")

    print("  - Generating Garmin sleep data...")
    sleep = generate_garmin_sleep(start_date, num_days=365)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__sleep AS SELECT * FROM sleep")
    print(f"    {len(sleep):,} sleep records")

    print("  - Generating Garmin health status (HRV, RHR)...")
    health = generate_garmin_health_status(start_date, num_days=365)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__health_status AS SELECT * FROM health")
    print(f"    {len(health):,} metrics")

    print("  - Generating Garmin training readiness...")
    readiness = generate_garmin_training_readiness(start_date, num_days=365)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__training_readiness AS SELECT * FROM readiness")
    print(f"    {len(readiness):,} readiness scores")

    # Create stub tables for optional Garmin sources (not used by agent but required by dbt)
    print("  - Creating agent-ready mart and intermediate tables...")

    # Create main_marts.fct_activity with all agent-expected columns
    con.execute("CREATE SCHEMA IF NOT EXISTS main_marts")
    con.execute("CREATE SCHEMA IF NOT EXISTS main_intermediate")

    con.execute("""
        CREATE OR REPLACE TABLE main_marts.fct_activity AS
        SELECT
            s.activity_id,
            s.activity_name,
            s.activity_type,
            s.activity_date,
            s.started_at,
            ROUND(s.distance, 2) as distance_km,
            ROUND(s.elapsed_time * 3600, 0) as moving_time_s,
            ROUND(s.average_heartrate, 1) as average_heart_rate_bpm,
            s.max_heart_rate as max_heart_rate_bpm,
            ROUND(s.distance / NULLIF(s.elapsed_time / 60, 0), 1) as average_speed_kph,
            ROUND(s.elevation_gain, 0) as elevation_gain_m,
            ROUND(s.average_heartrate * 0.8, 1) as average_watts,
            ROUND(RANDOM() * 5 + 1, 1) as aerobic_training_effect,
            ROUND(RANDOM() * 3, 1) as anaerobic_training_effect,
            'Base' as training_effect_label,
            CAST(RANDOM() * 50 + 30 AS INTEGER) as activity_training_load,
            CAST(RANDOM() * 200 + 50 AS INTEGER) as relative_effort,
            CAST(RANDOM() * 1800 AS INTEGER) as hr_zone_2_s,
            CAST(RANDOM() * 600 AS INTEGER) as hr_zone_5_s,
            COALESCE(tr.training_readiness_score, 50) as readiness_score,
            CASE WHEN COALESCE(tr.training_readiness_score, 50) > 70 THEN 'PRIME'
                 WHEN COALESCE(tr.training_readiness_score, 50) > 55 THEN 'MODERATE'
                 ELSE 'LOW' END as readiness_level,
            ROUND(RANDOM() * 3 + 1, 1) as recovery_time_h,
            ROUND(15.0 + RANDOM() * 15, 1) as weather_temperature_c,
            ROUND(15.0 + RANDOM() * 15, 1) as apparent_temperature_c,
            ROUND(RANDOM(), 2) as humidity_fraction,
            ROUND(RANDOM() * 10, 1) as wind_speed_ms
        FROM raw.strava__activities s
        LEFT JOIN raw.garmin__training_readiness tr ON DATE(s.started_at) = tr.calendar_date
        ORDER BY s.started_at DESC
    """)

    con.execute("""
        CREATE OR REPLACE TABLE main_intermediate.int_garmin__daily AS
        SELECT
            d.calendar_date,
            COALESCE(tr.training_readiness_score, 50) as readiness_score,
            CASE WHEN COALESCE(tr.training_readiness_score, 50) > 70 THEN 'PRIME'
                 WHEN COALESCE(tr.training_readiness_score, 50) > 55 THEN 'MODERATE'
                 ELSE 'LOW' END as readiness_level,
            'Status good' as readiness_feedback_short,
            'PEAKING' as training_status,
            ROUND(60.0 + RANDOM() * 30, 1) as hrv_ms,
            30.0 as hrv_baseline_lower_ms,
            100.0 as hrv_baseline_upper_ms,
            CASE WHEN (60.0 + RANDOM() * 30) > 65 THEN 'GOOD' ELSE 'BALANCED' END as hrv_status,
            COALESCE(s.sleep_score_overall, 70) as sleep_score,
            ROUND((COALESCE(s.deep_sleep_seconds, 0) + COALESCE(s.light_sleep_seconds, 0) + COALESCE(s.rem_sleep_seconds, 0)) / 3600.0, 2) as total_sleep_s,
            ROUND(COALESCE(s.deep_sleep_seconds, 0) / 3600.0, 2) as deep_sleep_s,
            ROUND(COALESCE(s.rem_sleep_seconds, 0) / 3600.0, 2) as rem_sleep_s,
            COALESCE(s.sleep_score_recovery, 70) as sleep_score_recovery,
            COALESCE(s.sleep_score_overall, 70) * 0.9 as sleep_score_restfulness,
            'Sleep was good' as sleep_score_feedback,
            CAST(d.stress_avg_total AS INTEGER) as stress_avg,
            CAST(d.stress_avg_awake AS INTEGER) as stress_avg_awake,
            d.body_battery_highest,
            d.body_battery_lowest,
            CAST(RANDOM() * 30 + 10 AS INTEGER) as body_battery_gained_during_sleep,
            d.body_battery_start_of_day,
            d.body_battery_end_of_day,
            d.current_day_resting_heart_rate as current_resting_hr_bpm,
            d.resting_heart_rate as resting_hr_7d_avg_bpm,
            15 as avg_waking_respiration_brpm,
            d.total_steps,
            d.active_kilocalories as active_kcal,
            d.is_vigorous_day,
            ROUND(RANDOM() * 2 + 1, 1) as recovery_time_h,
            'Good recovery' as recovery_time_factor_feedback,
            ROUND(0.5 + RANDOM() * 0.5, 2) as acwr,
            'Balanced' as acwr_status
        FROM raw.garmin__daily_summary d
        LEFT JOIN raw.garmin__training_readiness tr ON d.calendar_date = tr.calendar_date
        LEFT JOIN raw.garmin__sleep s ON d.calendar_date = s.calendar_date
        ORDER BY d.calendar_date DESC
    """)

    print(f"    Created agent-ready mart tables")

    con.close()
    print(f"\nDone. Synthetic database: {DB_PATH}")
    print(f"  Use with: USE_SYNTHETIC_DATA=true streamlit run app.py")


if __name__ == "__main__":
    main()
