# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-05-15

### Added
- **Streamlit Cloud deployment support**
  - Auto-detection of cloud environment via `STREAMLIT_DEPLOYMENT_ID` secret
  - Anthropic-only provider on cloud (LM Studio disabled)
  - Synthetic demo dataset forced on cloud, ephemeral chat sessions
- **Empty state UX with example queries**
  - Clickable example prompts appear at start of each new chat
  - Improves first-time activation and discoverability
- **`generate_chart` tool** for time-series visualizations
  - Supports activity metrics (power, pace, distance), health trends (HRV, sleep, readiness), run pace progression
  - Renders inline in Streamlit UI using Plotly
- **Synthetic data generator** (`scripts/generate_sample_data.py`)
  - ~200 realistic activities with sport-specific distributions
  - 365 days of daily health metrics (HRV, sleep, readiness, body battery)
  - Statistically grounded ranges; reproducible with fixed seed

### Fixed
- **Security**: API keys now session-only (never persisted to disk on cloud)
- **Security**: Chat history ephemeral on cloud (no cross-user data leakage)
- **Database connectivity**: Fixed environment variable syncing for synthetic data selection
- **Duplicate messages**: Chat history no longer shows previous message twice
- **Import errors**: Fixed `main.py` import on Streamlit Cloud
- **Error messages**: Database errors now show detailed diagnostics instead of generic "offline" message

### Changed
- Default Claude model to `claude-haiku-4-5` (from sonnet)
- Local/cloud modes now have distinct UI and behavior
- Chat persistence disabled on cloud (kept on local for development)

## [0.1.0] - 2026-05-06

### Added
- Initial release (V0.1)
- Multi-tool conversational AI agent with LangChain/LangGraph
  - `query_activities` tool for workout-specific questions
  - `query_daily_health` tool for physiological metrics (HRV, sleep, readiness)
  - Supports Anthropic Claude and local LM Studio inference
- Streamlit UI (`app.py`) with chat history persistence
- Terminal REPL agent interface (`main.py`)
- Complete dbt analytics pipeline
  - 12 staging models (Strava + Garmin data)
  - 1 intermediate model (daily health mart)
  - 3 fact tables (activity, ride, run)
- Statistical analysis notebook
  - OLS regression study: physiological readiness vs. athletic performance
  - 5-fold cross-validation analysis
  - Model diagnostics and coefficient plots
- Full setup instructions and `.env.example` configuration

### Notes
- **Data not included**: Personal Strava and Garmin exports are gitignored. Synthetic data generator planned for future release.
- **Web UI not deployed**: V0.1 supports local Streamlit + terminal interfaces only.
- **License**: MIT with Commons Clause (non-commercial use without permission).
