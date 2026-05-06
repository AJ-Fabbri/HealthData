# Changelog

All notable changes to this project will be documented in this file.

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
