"""
LangChain tools backed by the DuckDB mart tables.

Readiness levels stored in DB: PRIME, HIGH, MODERATE, LOW, POOR
Activity types (common): Ride, Run, Walk, Hike, Workout, Weight Training,
                          Alpine Ski, Backcountry Ski, Rock Climb, Yoga,
                          Elliptical, Crossfit, Kayaking, Golf
"""

from __future__ import annotations

import math
import re
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from langchain_core.tools import tool

from .db import get_conn

from datetime import datetime


def _json_safe(v):
    """Convert non-JSON-serialisable values to serialisable equivalents."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _build_conditions(
    sport_type: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    readiness_tier: Optional[str],
    table_alias: str = "",
) -> tuple[list[str], list]:
    prefix = f"{table_alias}." if table_alias else ""
    conditions: list[str] = []
    params: list = []
    if sport_type and sport_type.lower() != "all":
        conditions.append(f"LOWER({prefix}activity_type) = LOWER(?)")
        params.append(sport_type)
    if start_date:
        conditions.append(f"{prefix}activity_date >= CAST(? AS DATE)")
        params.append(start_date)
    if end_date:
        conditions.append(f"{prefix}activity_date <= CAST(? AS DATE)")
        params.append(end_date)
    if readiness_tier:
        conditions.append(f"UPPER({prefix}readiness_level) = UPPER(?)")
        params.append(readiness_tier)
    return conditions, params


# ---------------------------------------------------------------------------
# Pre-built query tools
# ---------------------------------------------------------------------------


@tool
def query_activities(
    sport_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    readiness_tier: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Return recent activities with key performance and health context.

    Parameters
    ----------
    sport_type : str, optional
        e.g. "Ride", "Run", "Hike". Pass "all" or omit for every sport.
    start_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    end_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    readiness_tier : str, optional
        "PRIME", "HIGH", "MODERATE", "LOW", or "POOR". Case-insensitive.
    limit : int, optional
        Max activity rows to return, newest first (default 20).

    Returns
    -------
    dict with "count", "aggregates", and "activities" list (date, sport, name,
    distance_km, moving_time_min, avg_hr, average_watts, avg_speed_kph,
    elevation_gain_m, readiness_score, readiness_level, sleep_score, hrv_ms,
    factor feedbacks, weather fields).
    """
    con = get_conn()

    conds, params = _build_conditions(sport_type, start_date, end_date, readiness_tier)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    conds_fa, params_fa = _build_conditions(
        sport_type, start_date, end_date, readiness_tier, table_alias="fa"
    )
    where_fa = ("WHERE " + " AND ".join(conds_fa)) if conds_fa else ""

    total = con.execute(
        f"SELECT COUNT(*) FROM main_marts.fct_activity {where}", params
    ).fetchone()[0]

    agg_df = con.execute(
        f"""
        SELECT
            COUNT(*)                                     AS n_activities,
            ROUND(AVG(fa.distance_km), 2)                AS avg_distance_km,
            ROUND(AVG(fa.moving_time_s) / 60.0, 1)       AS avg_moving_time_min,
            ROUND(AVG(fa.average_heart_rate_bpm), 1)      AS avg_hr_bpm,
            ROUND(AVG(fa.relative_effort), 1)            AS avg_strava_relative_effort,
            ROUND(AVG(fa.activity_training_load), 1)      AS avg_garmin_training_load,
            ROUND(AVG(fa.readiness_score), 1)             AS avg_readiness_score
        FROM main_marts.fct_activity fa
        {where_fa}
        """,
        params_fa,
    ).fetchdf()
    aggregates = {
        k: v
        for k, v in agg_df.to_dict(orient="records")[0].items()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }

    rows_df = con.execute(
        f"""
        SELECT
            activity_date::VARCHAR              AS date,
            activity_type                       AS sport,
            activity_name                       AS name,
            
            -- Spatial & Temporal Performance
            ROUND(distance_km, 2)               AS distance_km,
            ROUND(moving_time_s / 60.0, 1)      AS moving_time_min,
            ROUND(average_speed_kph, 1)         AS avg_speed_kph,
            ROUND(elevation_gain_m, 0)          AS elevation_gain_m,
            
            -- Cardiac Metrics
            average_heart_rate_bpm              AS avg_hr,
            max_heart_rate_bpm                  AS max_hr,
            
            -- Mechanical Output (Strava Estimated Watts only)
            average_watts,
            
            -- Physiological Impact & Training Load (Garmin & Strava metrics combined)
            ROUND(aerobic_training_effect, 1)   AS aerobic_training_effect,
            ROUND(anaerobic_training_effect, 1) AS anaerobic_training_effect,
            training_effect_label,              -- E.g. "VO2 Max", "Threshold", "Base", "Recovery"
            activity_training_load,             -- Raw physiological stimulus score
            relative_effort,                    -- Cardiac fatigue score (Strava)
            
            -- HR Zone Distribution (Aerobic Base vs. Anaerobic/VO2 Max limits)
            ROUND(hr_zone_2_s / 60.0, 1)        AS zone_2_aerobic_min,
            ROUND(hr_zone_5_s / 60.0, 1)        AS zone_5_anaerobic_min,
            
            -- Same-Day Readiness Context
            readiness_score,
            readiness_level,
            recovery_time_h                     AS residual_recovery_needed_h,
            
            -- Environmental Factors
            ROUND(weather_temperature_c, 1)     AS temperature_c,
            ROUND(apparent_temperature_c, 1)    AS feels_like_c,
            ROUND(humidity_fraction * 100, 0)   AS humidity_pct,
            ROUND(wind_speed_ms, 1)             AS wind_speed_ms
        FROM main_marts.fct_activity
        {where}
        ORDER BY activity_date DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchdf()

    activities = rows_df.where(rows_df.notna(), other=None).to_dict(orient="records")
    return {"count": total, "aggregates": aggregates, "activities": activities}


@tool
def query_daily_health(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Return the daily health time series — one row per calendar day including
    rest days. Use for health trends, HRV, sleep, body battery, stress.

    Parameters
    ----------
    start_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    end_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    limit : int, optional
        Max rows to return, newest first (default 20).

    Returns
    -------
    dict with "count", "aggregates", and "days" list (calendar_date,
    readiness_score/level, hrv_ms + baseline, sleep_score, total_sleep_h,
    deep_sleep_h, rem_sleep_h, body_battery_start/highest, stress_avg,
    resting_hr_7d_avg_bpm, recovery_time_h, acwr, training_status,
    factor feedbacks).
    """
    con = get_conn()

    conds: list[str] = []
    params: list = []
    
    # Date parsing & auto-correction block
    for date_name, date_val in [("start_date", start_date), ("end_date", end_date)]:
        if date_val:
            parsed_date = None
            # Try YYYY-MM-DD first, fall back to YYYY-DD-MM if the agent flips them
            for fmt in ("%Y-%m-%d", "%Y-%d-%m"):
                try:
                    parsed_date = datetime.strptime(date_val, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not parsed_date:
                raise ValueError(
                    f"Invalid date format for {date_name}: '{date_val}'. "
                    f"Please use ISO format (YYYY-MM-DD)."
                )
            
            # Format explicitly to YYYY-MM-DD for the database
            safe_date_str = parsed_date.strftime("%Y-%m-%d")
            
            if date_name == "start_date":
                conds.append("calendar_date >= CAST(? AS DATE)")
            else:
                conds.append("calendar_date <= CAST(? AS DATE)")
                
            params.append(safe_date_str)
    # .join takes conds strings and joins them with " AND " between them
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    total = con.execute(
        f"SELECT COUNT(*) FROM main_intermediate.int_garmin__daily {where}", params
    ).fetchone()[0]

    agg_df = con.execute(
        f"""
        SELECT
            COUNT(*)                                        AS n_days,
            ROUND(AVG(readiness_score), 1)                  AS avg_readiness_score,
            ROUND(AVG(hrv_ms), 1)                           AS avg_hrv_ms,
            ROUND(AVG(sleep_score), 1)                      AS avg_sleep_score,
            ROUND(AVG(total_sleep_s) / 3600.0, 2)           AS avg_sleep_h,
            ROUND(AVG(current_resting_hr_bpm), 1)           AS avg_resting_hr_bpm,
            ROUND(AVG(stress_avg), 1)                       AS avg_stress_score,
            ROUND(AVG(active_kcal), 0)                      AS avg_active_kcal,
            ROUND(AVG(total_steps), 0)                      AS avg_steps
        FROM main_intermediate.int_garmin__daily
        {where}
        """,
        params,
    ).fetchdf()
    aggregates = {
        k: v
        for k, v in agg_df.to_dict(orient="records")[0].items()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }

    rows_df = con.execute(
        f"""
        SELECT
            calendar_date::VARCHAR                              AS calendar_date,
            
            -- Readiness & Status
            readiness_score,
            readiness_level,
            readiness_feedback_short,
            training_status,
            
            -- HRV Status (Both actual millisecond values & relative baseline)
            ROUND(hrv_ms, 1)                                   AS hrv_ms,
            ROUND(hrv_baseline_lower_ms, 1)                    AS hrv_baseline_lower_ms,
            ROUND(hrv_baseline_upper_ms, 1)                    AS hrv_baseline_upper_ms,
            hrv_status,
            
            -- Sleep Architecture & Quality
            sleep_score,
            ROUND(total_sleep_s / 3600.0, 2)                   AS total_sleep_h,
            ROUND(deep_sleep_s  / 3600.0, 2)                   AS deep_sleep_h,
            ROUND(rem_sleep_s   / 3600.0, 2)                   AS rem_sleep_h,
            sleep_score_recovery,                               -- Specific sleep recovery rating
            sleep_score_restfulness,                            -- Toss/turn/wake score
            sleep_score_feedback,
            
            -- Stress & Battery
            stress_avg,
            stress_avg_awake,
            body_battery_highest,
            body_battery_lowest,
            body_battery_gained_during_sleep,
            
            -- Cardiovascular & Respiratory
            current_resting_hr_bpm,                             -- True same-day resting HR
            resting_hr_7d_avg_bpm,                              -- 7-day baseline
            avg_waking_respiration_brpm,
            
            -- Daily Strain & Activity Context (Allows agent to correlate why health metrics fluctuate)
            total_steps,
            active_kcal,
            is_vigorous_day,
            
            -- Recovery Time & Training Load
            recovery_time_h,
            recovery_time_factor_feedback,
            ROUND(acwr, 2)                                     AS acwr,
            acwr_status
        FROM main_intermediate.int_garmin__daily
        {where}
        ORDER BY calendar_date DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchdf()

    days = rows_df.where(rows_df.notna(), other=None).to_dict(orient="records")
    return {"count": total, "aggregates": aggregates, "days": days}


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

_CHART_CONFIGS: dict[str, dict] = {
    "activity": {
        "table": "main_marts.fct_activity",
        "date_col": "activity_date",
        "name_col": "activity_name",
        "has_sport_filter": True,
        "metrics": {
            "avg_speed_kph": ("ROUND(average_speed_kph, 2)", "Avg Speed (km/h)"),
            "distance_km": ("ROUND(distance_km, 2)", "Distance (km)"),
            "elevation_gain_m": ("ROUND(elevation_gain_m, 0)", "Elevation Gain (m)"),
            "average_watts": ("ROUND(average_watts, 1)", "Avg Power (W)"),
            "average_heart_rate_bpm": ("average_heart_rate_bpm", "Avg HR (bpm)"),
            "moving_time_min": ("ROUND(moving_time_s / 60.0, 1)", "Moving Time (min)"),
            "relative_effort": ("ROUND(relative_effort, 0)", "Relative Effort"),
            "calories_kcal": ("calories_kcal", "Calories (kcal)"),
        },
    },
    "health": {
        "table": "main_intermediate.int_garmin__daily",
        "date_col": "calendar_date",
        "name_col": None,
        "has_sport_filter": False,
        "metrics": {
            "hrv_ms": ("ROUND(hrv_ms, 1)", "HRV (ms)"),
            "sleep_score": ("sleep_score", "Sleep Score"),
            "readiness_score": ("readiness_score", "Readiness Score"),
            "body_battery_start_of_day": ("body_battery_start_of_day", "Body Battery (start of day)"),
            "stress_avg": ("stress_avg", "Avg Stress"),
            "total_sleep_h": ("ROUND(total_sleep_s / 3600.0, 2)", "Total Sleep (h)"),
            "recovery_time_h": ("recovery_time_h", "Recovery Time (h)"),
            "resting_hr_7d_avg_bpm": ("ROUND(resting_hr_7d_avg_bpm, 1)", "Resting HR 7d avg (bpm)"),
        },
    },
    "run_pace": {
        "table": "main_marts.fct_run",
        "date_col": "activity_date",
        "name_col": "activity_name",
        "has_sport_filter": False,
        "metrics": {
            "pace_min_per_km": ("ROUND(pace_min_per_km, 2)", "Pace (min/km) — lower is faster"),
            "gap_min_per_km": ("ROUND(gap_min_per_km, 2)", "Grade-Adjusted Pace (min/km) — lower is faster"),
        },
    },
    "ride_power": {
        "table": "main_marts.fct_ride",
        "date_col": "activity_date",
        "name_col": "activity_name",
        "has_sport_filter": False,
        "metrics": {
            "average_watts": ("ROUND(average_watts, 1)", "Avg Power (W)"),
            "weighted_average_power_w": ("ROUND(weighted_average_power_w, 1)", "Normalized Power (W)"),
            "average_wkg": ("ROUND(average_wkg, 3)", "Avg W/kg"),
        },
    },
    "race_predictions": {
        "table": "main_staging.stg_garmin__run_race_predictions",
        "date_col": "calendar_date",
        "name_col": None,
        "has_sport_filter": False,
        "metrics": {
            "predicted_5k_pace_min_per_km": ("ROUND(predicted_5k_pace_min_per_km, 2)", "Predicted 5K Pace (min/km)"),
            "predicted_10k_pace_min_per_km": ("ROUND(predicted_10k_pace_min_per_km, 2)", "Predicted 10K Pace (min/km)"),
            "predicted_half_pace_min_per_km": ("ROUND(predicted_half_pace_min_per_km, 2)", "Predicted Half Marathon Pace (min/km)"),
            "predicted_marathon_pace_min_per_km": ("ROUND(predicted_marathon_pace_min_per_km, 2)", "Predicted Marathon Pace (min/km)"),
        },
    },
}


@tool
def generate_chart(
    chart_type: str,
    metric: str,
    sport_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    rolling_days: int = 0,
) -> dict:
    """
    Generate a time-series chart and return it as a Plotly figure.

    Parameters
    ----------
    chart_type : str
        One of: "activity", "health", "run_pace", "ride_power", "race_predictions"
    metric : str
        activity: avg_speed_kph, distance_km, elevation_gain_m, average_watts, average_heart_rate_bpm, moving_time_min, relative_effort, calories_kcal
        health: hrv_ms, sleep_score, readiness_score, body_battery_start_of_day, stress_avg, total_sleep_h, recovery_time_h, resting_hr_7d_avg_bpm
        run_pace: pace_min_per_km, gap_min_per_km
        ride_power: average_watts, weighted_average_power_w, average_wkg
        race_predictions: predicted_5k_pace_min_per_km, predicted_10k_pace_min_per_km, predicted_half_pace_min_per_km, predicted_marathon_pace_min_per_km
    sport_type : str, optional
        Activity type filter, only for chart_type="activity". E.g. "Ride", "Run".
    start_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    end_date : str, optional
        ISO date (YYYY-MM-DD), inclusive.
    rolling_days : int, optional
        Rolling average window in data points (0 = off). Typical: 7, 14, 28.

    Returns
    -------
    dict with "_chart_json" (rendered by UI automatically), "summary" (include
    in reply), "data_points"; or "error" on failure.
    """
    cfg = _CHART_CONFIGS.get(chart_type)
    if cfg is None:
        return {"error": f"Unknown chart_type '{chart_type}'. Valid: {list(_CHART_CONFIGS)}"}

    metric_info = cfg["metrics"].get(metric)
    if metric_info is None:
        return {"error": f"Unknown metric '{metric}' for '{chart_type}'. Valid: {list(cfg['metrics'])}"}

    metric_expr, y_label = metric_info
    date_col = cfg["date_col"]
    table = cfg["table"]
    name_col = cfg["name_col"]

    conds: list[str] = [f"{metric_expr} IS NOT NULL"]
    params: list = []

    if cfg["has_sport_filter"] and sport_type and sport_type.lower() != "all":
        conds.append("LOWER(activity_type) = LOWER(?)")
        params.append(sport_type)
    if start_date:
        conds.append(f"{date_col} >= CAST(? AS DATE)")
        params.append(start_date)
    if end_date:
        conds.append(f"{date_col} <= CAST(? AS DATE)")
        params.append(end_date)

    where = "WHERE " + " AND ".join(conds)
    name_select = f", {name_col} AS label" if name_col else ", NULL AS label"

    try:
        con = get_conn()
        rows_df = con.execute(
            f"""
            SELECT {date_col}::VARCHAR AS date, {metric_expr} AS value {name_select}
            FROM {table} {where} ORDER BY {date_col}
            """,
            params,
        ).fetchdf()
    except Exception as exc:
        return {"error": str(exc)}

    rows_df = rows_df.dropna(subset=["value"])
    if rows_df.empty:
        return {"error": "No data found for the requested filters."}

    rows_df["date"] = pd.to_datetime(rows_df["date"])

    hover = (
        "<b>%{customdata}</b><br>%{x|%Y-%m-%d}<br>" + y_label + ": %{y}<extra></extra>"
        if name_col
        else "%{x|%Y-%m-%d}<br>" + y_label + ": %{y}<extra></extra>"
    )
    traces: list[go.BaseTraceType] = [
        go.Scatter(
            x=rows_df["date"], y=rows_df["value"], mode="markers", name=y_label,
            customdata=rows_df["label"] if name_col else None,
            hovertemplate=hover, marker=dict(size=6, opacity=0.55),
        )
    ]

    if rolling_days > 0:
        rolled = (
            rows_df["value"]
            .rolling(window=rolling_days, min_periods=max(1, rolling_days // 2))
            .mean().round(2)
        )
        traces.append(go.Scatter(
            x=rows_df["date"], y=rolled, mode="lines",
            name=f"{rolling_days}-point avg", line=dict(width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>Rolling avg: %{y}<extra></extra>",
        ))

    sport_label = f" — {sport_type}" if sport_type and sport_type.lower() != "all" else ""
    date_range = ""
    if start_date or end_date:
        lo = start_date or rows_df["date"].min().strftime("%Y-%m-%d")
        hi = end_date or rows_df["date"].max().strftime("%Y-%m-%d")
        date_range = f" ({lo} to {hi})"
    title = f"{y_label}{sport_label}{date_range}"

    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            title=title, xaxis=dict(title="Date"), yaxis=dict(title=y_label),
            template="plotly_white", height=440,
            margin=dict(l=50, r=20, t=50, b=90),
            legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        ),
    )

    d_min = rows_df["date"].min().strftime("%Y-%m-%d")
    d_max = rows_df["date"].max().strftime("%Y-%m-%d")
    n = len(rows_df)
    return {
        "_chart_json": fig.to_json(),
        "summary": f"Chart: {title} — {n} data point{'s' if n != 1 else ''} from {d_min} to {d_max}.",
        "data_points": n,
    }
