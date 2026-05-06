#!/usr/bin/env python3
"""
Ingest raw Strava and Garmin export files into a local DuckDB database.

Run from the repo root:
    python scripts/ingest.py

Creates raw source tables in the 'raw' schema of data/healthdata.duckdb:
    raw.strava__activities
    raw.garmin__health_status          (metrics array unnested to long format)
    raw.garmin__sleep                  (sleepScores sub-object flattened)
    raw.garmin__daily_summary          (nested allDayStress / bodyBattery / respiration flattened)
    raw.garmin__activities             (summarizedActivitiesExport wrapper removed)
    raw.garmin__training_readiness
    raw.garmin__training_load
    raw.garmin__training_status
    raw.garmin__vo2max
    raw.garmin__endurance_score        (enduranceScoreContributor array extracted to columns)
    raw.garmin__hill_score
    raw.garmin__run_race_predictions
"""

import glob
import json
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
GARMIN_DIR = DATA_DIR / "Garmin_All_Apr4" / "DI_CONNECT"
STRAVA_DIR = DATA_DIR / "Strava_All_Apr4"
DB_PATH = DATA_DIR / "healthdata.duckdb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json_files(pattern: str) -> list[dict]:
    """Concatenate all JSON files matching a glob pattern (each file is a JSON array)."""
    records = []
    paths = sorted(glob.glob(pattern))
    if not paths:
        print(f"  WARNING: no files found for pattern {pattern}", file=sys.stderr)
        return records
    for path in paths:
        with open(path) as f:
            data = json.load(f)
        records.extend(data if isinstance(data, list) else [data])
    return records


def to_snake_case(name: str) -> str:
    """Convert camelCase / PascalCase / Title Case (with spaces) to snake_case."""
    s = name.replace(" ", "_")
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()
    return re.sub(r"_+", "_", s)


# ---------------------------------------------------------------------------
# Strava
# ---------------------------------------------------------------------------

def ingest_strava_activities(con: duckdb.DuckDBPyConnection) -> None:
    """
    Load activities.csv handling the 5 duplicate column names.

    pandas adds a '.1' suffix to the second occurrence of a duplicate header.
    The second occurrence (higher column index) is the detailed/precise version
    from Strava's data and becomes the canonical column name in the raw table.
    """
    csv_path = STRAVA_DIR / "activities.csv"
    df = pd.read_csv(csv_path, low_memory=False)

    # Duplicate columns: first occurrence -> _summary variant; second -> canonical
    rename_map = {
        "Elapsed Time":   "elapsed_time_summary",
        "Distance":       "distance_summary",
        "Max Heart Rate": "max_heart_rate_summary",
        "Relative Effort": "relative_effort_summary",
        "Commute":        "commute_summary",
        # Second (detailed) occurrences get the canonical snake_case name
        "Elapsed Time.1":   "elapsed_time",
        "Distance.1":       "distance",
        "Max Heart Rate.1": "max_heart_rate",
        "Relative Effort.1": "relative_effort",
        "Commute.1":        "commute",
        # Preserve the raw date string so it can be parsed separately below
        "Activity Date":    "activity_date_str",
    }
    df = df.rename(columns=rename_map)
    # Rename remaining columns to snake_case
    df.columns = [rename_map.get(c, to_snake_case(c)) for c in df.columns]

    # Change the human-readable date string to ISO datetime string
    # Example: "May 6, 2018, 5:38:31 PM"
    df["activity_date_str"] = df["activity_date_str"].astype(str)
    df["started_at"] = pd.to_datetime(df["activity_date_str"], format="mixed", dayfirst=False)
    df["activity_date"] = df["started_at"].dt.date

    con.execute("CREATE OR REPLACE TABLE raw.strava__activities AS SELECT * FROM df")
    print(f"  strava__activities: {len(df):,} rows")


# ---------------------------------------------------------------------------
# Garmin — Wellness
# ---------------------------------------------------------------------------

def ingest_garmin_health_status(con: duckdb.DuckDBPyConnection) -> None:
    """
    Load healthStatusData, unnesting the metrics array to long format.
    Each day produces 5 rows (one per metric type: HRV, HR, SPO2, SKIN_TEMP_C, RESPIRATION).
    """
    pattern = str(GARMIN_DIR / "DI-Connect-Wellness" / "*_healthStatusData.json")
    raw_records = load_json_files(pattern)

    rows = []
    for record in raw_records:
        base = {
            "calendar_date": record["calendarDate"],
            "create_timestamp_utc": record.get("createTimestampUTC"),
            "update_timestamp_utc": record.get("updateTimestampUTC"),
            "outliers_count": record.get("outliersCount"),
        }
        for metric in record.get("metrics", []):
            rows.append({
                **base,
                "metric_type": metric["type"],
                "value": metric.get("value"),
                "baseline_upper_limit": metric.get("baselineUpperLimit"),
                "baseline_lower_limit": metric.get("baselineLowerLimit"),
                "status": metric.get("status"),
                "percentage": metric.get("percentage"),
                "feedback_key": metric.get("feedbackKey"),
            })

    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__health_status AS SELECT * FROM df")
    print(f"  garmin__health_status: {len(df):,} rows ({len(df)//5:,} days × 5 metrics)")


def ingest_garmin_sleep(con: duckdb.DuckDBPyConnection) -> None:
    """Load sleepData with the sleepScores sub-object flattened to scalar columns."""
    pattern = str(GARMIN_DIR / "DI-Connect-Wellness" / "*_sleepData.json")
    raw_records = load_json_files(pattern)

    rows = []
    for r in raw_records:
        scores = r.get("sleepScores") or {}
        rows.append({
            "calendar_date":                  r.get("calendarDate"),
            "sleep_start_timestamp_gmt":      r.get("sleepStartTimestampGMT"),
            "sleep_end_timestamp_gmt":        r.get("sleepEndTimestampGMT"),
            "sleep_window_confirmation_type": r.get("sleepWindowConfirmationType"),
            "deep_sleep_seconds":             r.get("deepSleepSeconds"),
            "light_sleep_seconds":            r.get("lightSleepSeconds"),
            "rem_sleep_seconds":              r.get("remSleepSeconds"),
            "awake_sleep_seconds":            r.get("awakeSleepSeconds"),
            "unmeasurable_seconds":           r.get("unmeasurableSeconds"),
            "average_respiration":            r.get("averageRespiration"),
            "lowest_respiration":             r.get("lowestRespiration"),
            "highest_respiration":            r.get("highestRespiration"),
            "awake_count":                    r.get("awakeCount"),
            "avg_sleep_stress":               r.get("avgSleepStress"),
            "retro":                          r.get("retro"),
            "restless_moment_count":          r.get("restlessMomentCount"),
            # sleepScores sub-object
            "sleep_score_overall":            scores.get("overallScore"),
            "sleep_score_quality":            scores.get("qualityScore"),
            "sleep_score_duration":           scores.get("durationScore"),
            "sleep_score_recovery":           scores.get("recoveryScore"),
            "sleep_score_deep":               scores.get("deepScore"),
            "sleep_score_rem":                scores.get("remScore"),
            "sleep_score_light":              scores.get("lightScore"),
            "sleep_score_awakenings_count":   scores.get("awakeningsCountScore"),
            "sleep_score_awake_time":         scores.get("awakeTimeScore"),
            "sleep_score_combined_awake":     scores.get("combinedAwakeScore"),
            "sleep_score_restfulness":        scores.get("restfulnessScore"),
            "sleep_score_interruptions":      scores.get("interruptionsScore"),
            "sleep_score_feedback":           scores.get("feedback"),
            "sleep_score_insight":            scores.get("insight"),
        })

    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__sleep AS SELECT * FROM df")
    print(f"  garmin__sleep: {len(df):,} rows")


def ingest_garmin_daily_summary(con: duckdb.DuckDBPyConnection) -> None:
    """
    Load UDSFile with nested allDayStress, bodyBattery, respiration, hydration flattened.
    Extracts: TOTAL + AWAKE stress aggregators; HIGHEST/LOWEST/STARTOFDAY/ENDOFDAY/
    SLEEPSTART/SLEEPEND/DURINGSLEEP body battery stat types.
    """
    pattern = str(GARMIN_DIR / "DI-Connect-Aggregator" / "UDSFile_*.json")
    raw_records = load_json_files(pattern)

    rows = []
    for r in raw_records:
        # --- allDayStress aggregators ---
        stress_total: dict = {}
        stress_awake: dict = {}
        for agg in (r.get("allDayStress") or {}).get("aggregatorList", []):
            atype = agg.get("type")
            if atype == "TOTAL":
                stress_total = agg
            elif atype == "AWAKE":
                stress_awake = agg

        # --- bodyBattery stat lookup ---
        # Garmin uses "statType" (no trailing 's') as the discriminator key
        bb = r.get("bodyBattery") or {}
        bb_stats = {s["bodyBatteryStatType"]: s.get("statsValue")
                    for s in bb.get("bodyBatteryStatList", [])
                    if "bodyBatteryStatType" in s}

        # --- respiration + hydration ---
        resp = r.get("respiration") or {}
        hydration = r.get("hydration") or {}

        rows.append({
            "user_profile_pk":             r.get("userProfilePK"),
            "calendar_date":               r.get("calendarDate"),
            "uuid":                        r.get("uuid"),
            "wellness_start_time_gmt":     r.get("wellnessStartTimeGmt"),
            "wellness_end_time_gmt":       r.get("wellnessEndTimeGmt"),
            "wellness_start_time_local":   r.get("wellnessStartTimeLocal"),
            "wellness_end_time_local":     r.get("wellnessEndTimeLocal"),
            "total_steps":                 r.get("totalSteps"),
            "daily_step_goal":             r.get("dailyStepGoal"),
            "total_distance_meters":       r.get("totalDistanceMeters"),
            "wellness_distance_meters":    r.get("wellnessDistanceMeters"),
            "total_kilocalories":          r.get("totalKilocalories"),
            "active_kilocalories":         r.get("activeKilocalories"),
            "bmr_kilocalories":            r.get("bmrKilocalories"),
            "wellness_kilocalories":       r.get("wellnessKilocalories"),
            "remaining_kilocalories":      r.get("remainingKilocalories"),
            "resting_calories_from_activity": r.get("restingCaloriesFromActivity"),
            "net_calorie_goal":            r.get("netCalorieGoal"),
            "highly_active_seconds":       r.get("highlyActiveSeconds"),
            "active_seconds":              r.get("activeSeconds"),
            "moderate_intensity_minutes":  r.get("moderateIntensityMinutes"),
            "vigorous_intensity_minutes":  r.get("vigorousIntensityMinutes"),
            "is_vigorous_day":             r.get("isVigorousDay"),
            "floors_ascended_in_meters":   r.get("floorsAscendedInMeters"),
            "floors_descended_in_meters":  r.get("floorsDescendedInMeters"),
            "user_intensity_minutes_goal": r.get("userIntensityMinutesGoal"),
            "user_floors_ascended_goal":   r.get("userFloorsAscendedGoal"),
            "min_heart_rate":              r.get("minHeartRate"),
            "max_heart_rate":              r.get("maxHeartRate"),
            "resting_heart_rate":          r.get("restingHeartRate"),
            "current_day_resting_heart_rate": r.get("currentDayRestingHeartRate"),
            "resting_heart_rate_timestamp_ms": r.get("restingHeartRateTimestamp"),
            "min_avg_heart_rate":          r.get("minAvgHeartRate"),
            "max_avg_heart_rate":          r.get("maxAvgHeartRate"),
            "average_monitoring_environment_altitude": r.get("averageMonitoringEnvironmentAltitude"),
            "includes_wellness_data":      r.get("includesWellnessData"),
            "includes_activity_data":      r.get("includesActivityData"),
            "includes_calorie_consumed_data": r.get("includesCalorieConsumedData"),
            # allDayStress — TOTAL aggregator
            "stress_avg_total":            stress_total.get("averageStressLevel"),
            "stress_max_total":            stress_total.get("maxStressLevel"),
            "stress_duration_total_s":     stress_total.get("stressDuration"),
            "stress_rest_duration_total_s": stress_total.get("restDuration"),
            # allDayStress — AWAKE aggregator
            "stress_avg_awake":            stress_awake.get("averageStressLevel"),
            # bodyBattery
            "body_battery_charged":        bb.get("chargedValue"),
            "body_battery_drained":        bb.get("drainedValue"),
            "body_battery_highest":        bb_stats.get("HIGHEST"),
            "body_battery_lowest":         bb_stats.get("LOWEST"),
            "body_battery_start_of_day":   bb_stats.get("STARTOFDAY"),
            "body_battery_end_of_day":     bb_stats.get("ENDOFDAY"),
            "body_battery_sleep_start":    bb_stats.get("SLEEPSTART"),
            "body_battery_sleep_end":      bb_stats.get("SLEEPEND"),
            "body_battery_during_sleep":   bb_stats.get("DURINGSLEEP"),
            # respiration
            "avg_waking_respiration":      resp.get("avgWakingRespirationValue"),
            "highest_respiration":         resp.get("highestRespirationValue"),
            "lowest_respiration":          resp.get("lowestRespirationValue"),
            "latest_respiration":          resp.get("latestRespirationValue"),
            "latest_respiration_time_gmt": resp.get("latestRespirationTimeGMT"),
            # hydration
            "hydration_value_ml":          hydration.get("valueInML"),
            "hydration_goal_ml":           hydration.get("goalInML"),
            "hydration_sweat_loss_ml":     hydration.get("sweatLossInML"),
            "hydration_adjusted_goal_ml":  hydration.get("adjustedGoalInML"),
        })

    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__daily_summary AS SELECT * FROM df")
    print(f"  garmin__daily_summary: {len(df):,} rows")


def ingest_garmin_activities(con: duckdb.DuckDBPyConnection) -> None:
    """
    Load summarizedActivities, removing the outer [{"summarizedActivitiesExport": [...]}] wrapper.
    Files are in DI-Connect-Wellness (not DI-Connect-Fitness as data dict states).
    """
    pattern = str(GARMIN_DIR / "DI-Connect-Fitness" / "*_summarizedActivities.json")
    records: list[dict] = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            outer = json.load(f)
        for item in outer:
            records.extend(item.get("summarizedActivitiesExport", []))

    if not records:
        print("  WARNING: no garmin__activities records found", file=sys.stderr)
        return

    df = clean_df(pd.DataFrame(records))
    df.columns = [to_snake_case(c) for c in df.columns]
    # Drop nested array/object columns not needed at the raw layer
    drop_cols = [c for c in df.columns
                 if df[c].dropna().apply(lambda x: isinstance(x, (list, dict))).any()]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__activities AS SELECT * FROM df")
    print(f"  garmin__activities: {len(df):,} rows")


# ---------------------------------------------------------------------------
# Garmin — Metrics
# ---------------------------------------------------------------------------

def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Replace float NaN with Python None so DuckDB treats missing values as NULL."""
    return df.where(pd.notnull(df), other=None)


def ingest_simple_json(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    pattern: str,
) -> None:
    """Load a simple JSON source (array of flat dicts) into a raw table."""
    records = load_json_files(pattern)
    if not records:
        return
    df = clean_df(pd.DataFrame(records))
    df.columns = [to_snake_case(c) for c in df.columns]
    con.execute(f"CREATE OR REPLACE TABLE raw.{table_name} AS SELECT * FROM df")
    print(f"  {table_name}: {len(df):,} rows")


def ingest_garmin_endurance_score(con: duckdb.DuckDBPyConnection) -> None:
    """
    Load EnduranceScore files, extracting enduranceScoreContributor array to
    per-sport columns (group 0=cycling, 1=running, 3=hiking/walking, 8=other aerobic).
    """
    pattern = str(GARMIN_DIR / "DI-Connect-Metrics" / "EnduranceScore_*.json")
    raw_records = load_json_files(pattern)

    rows = []
    for r in raw_records:
        # Some elements use group (int enum) and others use sport/subSport;
        # filter to group-keyed elements for the named sport breakdowns
        contributors = {c["group"]: c["contribution"]
                        for c in r.get("enduranceScoreContributor", [])
                        if "group" in c}
        rows.append({
            "user_profile_pk":               r.get("userProfilePK") or r.get("userProfilePk"),
            "calendar_date_ms":              r.get("calendarDate"),
            "timestamp_ms":                  r.get("timestamp"),
            "device_id":                     r.get("deviceId"),
            "overall_score":                 r.get("overallScore"),
            "classification":                r.get("classification"),
            "feedback_phrase":               r.get("feedbackPhrase"),
            "primary_training_device":       r.get("primaryTrainingDevice"),
            "cycling_contribution":          contributors.get(0),
            "running_contribution":          contributors.get(1),
            "hiking_walking_contribution":   contributors.get(3),
            "other_aerobic_contribution":    contributors.get(8),
        })

    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE raw.garmin__endurance_score AS SELECT * FROM df")
    print(f"  garmin__endurance_score: {len(df):,} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Database: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")

    print("\nIngesting sources...")
    ingest_strava_activities(con)
    ingest_garmin_health_status(con)
    ingest_garmin_sleep(con)
    ingest_garmin_daily_summary(con)
    ingest_garmin_activities(con)

    metrics = GARMIN_DIR / "DI-Connect-Metrics"
    ingest_simple_json(con, "garmin__training_readiness",
                       str(metrics / "TrainingReadinessDTO_*.json"))
    ingest_simple_json(con, "garmin__training_load",
                       str(metrics / "MetricsAcuteTrainingLoad_*.json"))
    ingest_simple_json(con, "garmin__training_status",
                       str(metrics / "TrainingHistory_*.json"))
    ingest_simple_json(con, "garmin__vo2max",
                       str(metrics / "MetricsMaxMetData_*.json"))
    ingest_garmin_endurance_score(con)
    ingest_simple_json(con, "garmin__hill_score",
                       str(metrics / "HillScore_*.json"))
    ingest_simple_json(con, "garmin__run_race_predictions",
                       str(metrics / "RunRacePredictions_*.json"))

    # Summary
    print("\nRow counts in raw schema:")
    tables = con.execute(
        "SELECT table_name, estimated_size FROM duckdb_tables() WHERE schema_name='raw' ORDER BY table_name"
    ).fetchall()
    for name, size in tables:
        print(f"  raw.{name}: ~{size:,} rows")

    con.close()
    print(f"\nDone. Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
