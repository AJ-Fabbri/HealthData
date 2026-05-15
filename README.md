# HealthData: Analytics Engineering & Agentic AI Platform (Strava + Garmin data)

> **Status:** Active personal project. Includes a synthetic dataset generator for demos and online deployment.

> **Demo App Link:** [https://healthdata-chat.streamlit.app](https://healthdata-chat.streamlit.app)

**Two main elements:**
Agentic LLM interface: 8 years of personal training data, queryable in plain English.

Research notebook: An OLS regression study on what factors predict athletic performance.

Both built from my own Strava and Garmin exports: ~1,400 activities merged with daily physiological metrics from a Garmin Fenix 7X Pro.

**Stack:** Python · dbt · DuckDB · LangChain · LangGraph · Streamlit · Anthropic Claude / LM Studio

---

## The Agent

A multi-tool conversational AI agent over the full dataset. The model routes questions to typed database tools, synthesizes across them, and answers in natural language.

**Example exchange (Qwen 3.5 4B):**

> **Q:** I did not feel great in March 2026. Was it due to something physiological, like health issues, or training load?

> **A:** March 2026 was primarily a training load issue, not a health crisis. You did three back-to-back alpine ski days (Mar 9–11) with 5,400 m descent each — a massive acute workload spike. ACWR hit 0.6–0.7 and training status flipped to STRAINED. HRV dropped to POOR on Mar 18–22 (46–56 ms, below your 49–77 ms baseline) and readiness bottomed at 50–53. By late March, readiness had rebounded to HIGH/PRIME, HRV returned to VERY_GOOD, and training status shifted back to PEAKING. This wasn't illness — it was accumulated fatigue from high volume.

The agent calls up to three tools per query, combining workout-level data with daily physiological context (HRV, sleep, readiness, ACWR, stress) to answer questions that neither source alone could answer.

### Tools


| Tool                 | Data source                                                | Use for                                                                                                                                             |
| -------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query_activities`   | `fct_activity` mart                                        | Workout-specific questions: pace, power, distance, effort                                                                                           |
| `query_daily_health` | `int_garmin__daily`                                        | Health and recovery trends, rest days, HRV/sleep/readiness over time                                                                                |
| `generate_chart`     | `fct_activity`, `fct_ride`, `fct_run`, `int_garmin__daily` | Time-series visualizations: activity metrics (power, pace, distance), health trends (HRV, sleep, readiness), run pace progression, race predictions |


### Setup

**Prerequisites:** Python 3.12+, DuckDB 1.3+. For local inference, LM Studio with a tool-capable model loaded (e.g. Llama 3.1 8B Instruct). For cloud inference, an Anthropic API key.

```bash
cp .env.example .env        # add ANTHROPIC_API_KEY or point at LM Studio
pip install -r requirements.txt
streamlit run app.py
```

Switch between Anthropic and LM Studio in the sidebar. Chat history auto-saves to `chats/`.

### Running with Demo Data

A **synthetic dataset** is included (`data/healthdata_synthetic.duckdb`) with realistic athlete data: ~200 activities and 365 days of daily metrics. Perfect for testing without personal data.

To use the demo dataset locally:

```bash
USE_SYNTHETIC_DATA=true streamlit run app.py
```

**What's in the synthetic dataset:**

- ~200 mixed activities (cycling, running, hiking, skiing, walking) with realistic distributions per activity type
- 365 days of daily summaries (steps, activity minutes, body battery, stress)
- Complete HRV, resting heart rate, and sleep metrics for pattern analysis
- Training readiness and training status scores
- Statistically grounded ranges: 40±12 km cycling, 10±2.5 km running, realistic heart rate zones per activity type

The demo data is **self-contained with no setup needed**. The generator script (`scripts/generate_sample_data.py`) shows how it was created and can be re-run to generate fresh data anytime.

### Cloud Deployment (Streamlit Cloud)

The app is optimized for deployment to [Streamlit Cloud](https://healthdata-chat.streamlit.app):

1. Push this repository to GitHub
2. Create a new Streamlit app pointing to `app.py`
3. Set your `ANTHROPIC_API_KEY` in Streamlit Cloud secrets
4. Deploy

On Streamlit Cloud, the app automatically:

- Uses the synthetic demo dataset (Strava/Garmin imports disabled)
- Enables Anthropic as the only LLM provider
- Keeps chats ephemeral (session-only, not persisted)

Each user brings their own API key—no shared credentials needed. Perfect for trying the agent without setting up local infrastructure.

---

## The Research

A separate statistical analysis on top of the same dbt pipeline, asking: *how well do physiological state metrics predict same-day training output?*

**Primary question:** Does Garmin's composite training readiness score predict cycling watts and running pace? Do the raw components (HRV, sleep quality, recovery time, ACWR, stress history) predict better than the composite?

**Approach:** Within-athlete OLS regression with 5-fold cross-validation. Three nested models:


| Model | Predictors                                                                  |
| ----- | --------------------------------------------------------------------------- |
| A     | Readiness score only                                                        |
| B     | Readiness score + weather + hour of day                                     |
| C     | 5 raw components (HRV, sleep, recovery time, ACWR, stress) + weather + hour |


**Key results — cycling (n=183):**


| Model                        | OLS R² | CV R²  |
| ---------------------------- | ------ | ------ |
| A — readiness only           | 0.023  | −0.089 |
| B — readiness + context      | 0.250  | +0.115 |
| C — raw components + context | 0.271  | +0.157 |


Model B explains 25% of in-sample variance and generalises (CV R²=+0.115). The gap between OLS and CV R² reflects moderate overfitting. Model A's OLS R²=0.023 with CV R²=−0.089 is telling: readiness has a moderately significant association (p=0.07) but zero standalone predictive power.

Two predictors drive nearly all the lift from A to B:

- **Hour of day** (β≈+3.1 W/hour, p<0.0001): later rides produce more power, likely reflecting circadian rhythm, caffeine, and warmup
- **Wind speed** (β≈+4.1 W per m/s, p=0.009): windier conditions mean higher recorded watts

Readiness survives the addition of these context variables with a stable coefficient (β≈+0.27–0.28 W per point in both Models A and B, p≈0.07–0.08), confirming it's not proxying for weather or time of day. Across the full 0–100 score range that's ~28 W.

Model C's most interesting finding: none of the five raw readiness components reach individual significance, yet collectively they outperform the composite. Because the composite captures something that no single ingredient recovers in a simple linear model, we can assume that Garmin's aggregation does some useful work. All VIFs < 2, so multicollinearity isn't the explanation.

**Runs (n=66–74):** OLS R² reaches 0.28–0.38 across models, but CV R² is negative throughout; the models are overfit. With 66 observations and 11 predictors, coefficient estimates are unreliable. The only strong signal is rain (β≈−1.2 min/km).

**Important limitation**: cycling power is Strava's estimated watts (speed/gradient/weight model), not a power meter. The dependent variable carries measurement noise beyond what a direct measurement would.

Full model diagnostics, coefficient plots, and VIF checks are in `notebooks/01_model_comparison.ipynb`.

---

## Architecture

```
Strava CSV + Garmin JSON exports
        │
        ▼
scripts/ingest.py          ← raw ingestion into DuckDB (raw schema)
        │
        ▼
health_pipeline/           ← dbt project (12 staging → 1 intermediate → 3 mart models)
        │
        ├──▶ notebooks/    ← OLS regression analysis
        │
        └──▶ agent/        ← LangChain/LangGraph tools + LLM connector
                │
                ├── main.py    ← terminal REPL
                └── app.py     ← Streamlit UI
```

### Data sources

**Strava** — activity-level metrics: distance, time, heart rate, estimated power, elevation, cadence, weather.

**Garmin** — daily physiological context: training readiness score (with HRV, sleep, recovery time, ACWR, and stress sub-scores), raw HRV, resting HR, sleep stage breakdown, body battery, training status, VO₂ max.

The dbt pipeline joins these at the day grain so every activity row carries the athlete's physiological state on that day.

---

## Data

No personal data is included in this repository. The following are gitignored and must be sourced independently:

- `data/healthdata.duckdb` — the built DuckDB database
- `data/raw/` — raw Strava CSV and Garmin JSON exports

To rebuild from your own exports: populate `data/raw/` with your Strava and Garmin data, run `python scripts/ingest.py`, then `cd health_pipeline && dbt run`.