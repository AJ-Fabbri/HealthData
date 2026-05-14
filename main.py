#!/usr/bin/env python3
"""
Terminal chat interface for the HealthData agent.

Usage:
    python main.py
    python main.py --base-url http://192.168.1.50:1234/v1
    python main.py --model "lmstudio-community/meta-llama-3.1-8b-instruct"

Type "exit" or press Ctrl-C / Ctrl-D to quit.
"""

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def _strip_reasoning(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Drop reasoning_content from AIMessage history before the next turn.

    CoT tokens are only useful during generation - storing them bloats the
    context window on every subsequent call without adding information.
    """
    cleaned = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.additional_kwargs.get("reasoning_content"):
            msg = msg.model_copy(
                update={"additional_kwargs": {
                    k: v for k, v in msg.additional_kwargs.items()
                    if k != "reasoning_content"
                }}
            )
        cleaned.append(msg)
    return cleaned

from agent.llm import build_llm
from agent.tools import (
    generate_chart,
    query_activities,
    query_daily_health,
)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a personal athletic performance assistant with access to a training \
database spanning 2018-2026. The database contains Strava activity records \
merged with Garmin health metrics for a single athlete.

IMPORTANT: Aim to answer in as few tool calls as possible. MAXIMUM 2. \
If you hit TWO, stop and answer with what you have.

Tool efficiency - aim to answer in as few tool calls as possible. MAXIMUM 2:
- Never call the same tool twice with the same or similar arguments. \
  If a SQL query fails, fix the specific error and retry once - don't explore \
  alternative approaches that require multiple additional calls.
- If you have data from at least one successful tool call, always provide a \
  complete answer using what you have. It is better to answer after one tool call \
  and wait for the user's response than to call multiple times.

The most recent date in the database is {max_date}. When the user says \
"recently", "lately", "these days", or does not specify a date range, \
interpret that as approximately the last 90 days ending on {max_date}, \
unless context suggests otherwise.

Available data:
- Sports: Ride (cycling), Run, Hike, Walk, Weight Training, Alpine Ski, \
Rock Climb, Yoga, Crossfit, and more.
- Per-activity metrics: distance, moving time, heart rate, power (watts, \
W/kg for rides), pace (min/km for runs), elevation, calories, cadence, HR zones.
- Garmin health context per day: readiness score/level (PRIME/HIGH/MODERATE/LOW/POOR), \
HRV, sleep score, recovery time, ACWR, stress, training status.
- Weather at time of activity: temperature, humidity, wind, precipitation.

Interpreting Garmin readiness factor feedback fields - these reflect Garmin's \
assessment of each factor relative to the athlete's own personal baseline, not \
population norms. Values: VERY_GOOD > GOOD > MODERATE > POOR. Use them together \
with the raw numbers for full context: e.g. hrv_factor_feedback alongside hrv_ms, \
sleep_score_factor_feedback alongside sleep_score, \
recovery_time_factor_feedback alongside recovery_time_h. \
readiness_feedback_short is Garmin's plain-language daily summary.
"""

TOOLS = [
    query_activities,
    query_daily_health,
    generate_chart,
]

# No hard tool-call cap. The model is trusted to stop itself via the system
# prompt. Recursion limit is the only backstop (5 tool calls).
_RECURSION_LIMIT = 10


def _get_max_date() -> str:
    """Return the most recent activity_date in the database as YYYY-MM-DD."""
    from agent.db import get_conn
    try:
        row = get_conn().execute(
            "SELECT MAX(activity_date)::VARCHAR FROM main_marts.fct_activity"
        ).fetchone()
        return row[0] if row and row[0] else "2026-04-04"
    except Exception:
        return "2026-04-04"


def build_agent(provider: str | None, base_url: str | None, model: str | None):
    max_date = _get_max_date()
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(max_date=max_date)
    llm = build_llm(provider=provider, base_url=base_url, model=model)
    return create_agent(llm, TOOLS, system_prompt=system_prompt, middleware=[])


def chat_loop(agent) -> None:
    history: list[BaseMessage] = []

    print("HealthData agent ready. Type 'exit' or press Ctrl-C to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("Goodbye.")
            break

        history.append(HumanMessage(content=user_input))

        try:
            result = agent.invoke(
                {"messages": history},
                config={"recursion_limit": _RECURSION_LIMIT},
            )
        except Exception as exc:
            print(f"\n[error] {exc}\n", file=sys.stderr)
            history.pop()  # don't keep the unanswered message
            continue

        # Guard against None result or empty message list (LangGraph edge cases)
        if not result or not result.get("messages"):
            print("\n[error] Agent returned no response.\n", file=sys.stderr)
            history.pop()
            continue

        # The graph returns the full message list; the last message is the reply.
        # Some thinking models (e.g. Qwen3) return None or whitespace content.
        reply_msg: AIMessage = result["messages"][-1]
        content = reply_msg.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
        reply: str = (content or "").strip()
        if not reply:
            reply = "(no text response - the model may have only returned tool calls)"
        print(f"\nAgent: {reply}\n")

        # Sync history with whatever the graph produced (includes tool messages)
        history = _strip_reasoning(result["messages"])


def main() -> None:
    parser = argparse.ArgumentParser(description="HealthData terminal agent")
    parser.add_argument(
        "--provider", default=None,
        help="LLM provider: 'lmstudio' (default) or 'anthropic'",
    )
    parser.add_argument("--base-url", default=None, help="LM Studio API base URL")
    parser.add_argument("--model", default=None, help="Model identifier")
    args = parser.parse_args()

    try:
        agent = build_agent(provider=args.provider, base_url=args.base_url, model=args.model)
    except Exception as exc:
        print(f"[fatal] Could not build agent: {exc}", file=sys.stderr)
        sys.exit(1)

    chat_loop(agent)


if __name__ == "__main__":
    main()
