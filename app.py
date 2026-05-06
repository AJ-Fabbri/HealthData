"""
Streamlit chat UI for the HealthData agent.

Run with:
    streamlit run app.py
"""

import json
import os
from datetime import datetime

import plotly.io as pio

from dotenv import load_dotenv
load_dotenv()


def _content_str(content) -> str:
    """Normalise LangChain message content to a plain string.

    OpenAI returns a str; Anthropic returns a list of content blocks like
    [{'type': 'text', 'text': '...'}]. Both are handled here.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content) if content else ""

import streamlit as st
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)

from langgraph.errors import GraphRecursionError

from main import _RECURSION_LIMIT, build_agent

def _strip_reasoning(messages: list) -> list:
    """Remove reasoning_content from AIMessage additional_kwargs before storing.

    CoT tokens are only useful during the generation step — keeping them in
    history wastes context window on every subsequent turn.
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


def _extract_charts(messages) -> list:
    """Scan tool messages for generate_chart results and return plotly figures."""
    figs = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
            if isinstance(data, dict) and "_chart_json" in data:
                figs.append(pio.from_json(data["_chart_json"]))
        except Exception:
            pass
    return figs

CHATS_DIR = os.path.join(os.path.dirname(__file__), "chats")
os.makedirs(CHATS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HealthData Agent",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Chat persistence helpers
# ---------------------------------------------------------------------------

def _chat_path(chat_id: str) -> str:
    return os.path.join(CHATS_DIR, f"{chat_id}.json")


def save_chat(chat_id: str, title: str, messages: list[BaseMessage]) -> None:
    with open(_chat_path(chat_id), "w") as f:
        json.dump(
            {
                "title": title,
                "updated_at": datetime.now().isoformat(),
                "messages": messages_to_dict(messages),
            },
            f,
        )


def load_chat(chat_id: str) -> tuple[str, list[BaseMessage]]:
    with open(_chat_path(chat_id)) as f:
        data = json.load(f)
    return data["title"], messages_from_dict(data["messages"])


def list_chats() -> list[dict]:
    """Return saved chats sorted by most-recently updated, newest first."""
    chats = []
    for fname in os.listdir(CHATS_DIR):
        if not fname.endswith(".json"):
            continue
        chat_id = fname[:-5]
        try:
            with open(_chat_path(chat_id)) as f:
                data = json.load(f)
            chats.append({
                "id": chat_id,
                "title": data.get("title", "Untitled"),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            pass
    return sorted(chats, key=lambda c: c["updated_at"], reverse=True)


def delete_chat(chat_id: str) -> None:
    path = _chat_path(chat_id)
    if os.path.exists(path):
        os.remove(path)


def _title_from_messages(messages: list[BaseMessage]) -> str:
    """Use the first human message (truncated) as the chat title."""
    for msg in messages:
        if isinstance(msg, HumanMessage) and _content_str(msg.content).strip():
            return _content_str(msg.content).strip()[:60]
    return "New chat"


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "chat_id" not in st.session_state:
    st.session_state.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
if "history" not in st.session_state:
    st.session_state.history: list[BaseMessage] = []

# Bump whenever tools.py changes to force the cached agent to rebuild.
_TOOLS_VERSION = "4"

_TOOL_LABELS: dict[str, str] = {
    "query_activities": "Querying activities",
    "query_daily_health": "Querying daily health data",
    "generate_chart": "Generating chart",
}

# ---------------------------------------------------------------------------
# Cached agent — rebuilt only when provider/connection settings or tool version change
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Connecting to model…")
def get_agent(provider: str, url: str, mdl: str, api_key: str, _version: str):
    if provider == "anthropic" and api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    return build_agent(provider=provider, base_url=url or None, model=mdl or None)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("HealthData Agent")

    # Model provider settings (collapsed by default)
    with st.expander("Model settings", expanded=False):
        provider = st.selectbox(
            "Provider",
            options=["lmstudio", "anthropic"],
            index=0 if os.environ.get("LLM_PROVIDER", "lmstudio") == "lmstudio" else 1,
        )

        if provider == "anthropic":
            api_key = st.text_input(
                "Anthropic API key",
                value=os.environ.get("ANTHROPIC_API_KEY", ""),
                type="password",
                help="Get yours at console.anthropic.com. Stored only in this session.",
            )
            model = st.text_input(
                "Model",
                value=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                help="e.g. claude-sonnet-4-6 or claude-opus-4-7",
            )
            base_url = ""
        else:
            api_key = ""
            base_url = st.text_input(
                "Base URL",
                value=os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
                help="Change to point at a remote LM Studio instance.",
            )
            model = st.text_input(
                "Model name",
                value=os.environ.get("LM_STUDIO_MODEL", "local-model"),
                help="Must match the identifier shown in LM Studio.",
            )

    agent = get_agent(provider, base_url, model, api_key, _TOOLS_VERSION)

    st.divider()

    # New chat button
    if st.button("＋  New chat", width='stretch'):
        if st.session_state.history:
            save_chat(
                st.session_state.chat_id,
                _title_from_messages(st.session_state.history),
                st.session_state.history,
            )
        st.session_state.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        st.session_state.history = []
        st.rerun()

    st.divider()

    # Saved chats list
    saved = list_chats()
    if saved:
        st.caption("Recent chats")
        for chat in saved:
            col_btn, col_del = st.columns([5, 1])
            is_active = chat["id"] == st.session_state.chat_id
            label = ("**" + chat["title"] + "**") if is_active else chat["title"]
            if col_btn.button(label, key=f"load_{chat['id']}", width='stretch'):
                if st.session_state.history:
                    save_chat(
                        st.session_state.chat_id,
                        _title_from_messages(st.session_state.history),
                        st.session_state.history,
                    )
                _, msgs = load_chat(chat["id"])
                st.session_state.chat_id = chat["id"]
                st.session_state.history = msgs
                st.rerun()
            if col_del.button("✕", key=f"del_{chat['id']}"):
                delete_chat(chat["id"])
                if chat["id"] == st.session_state.chat_id:
                    st.session_state.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    st.session_state.history = []
                st.rerun()

    st.divider()
    provider_label = "Anthropic" if provider == "anthropic" else "LM Studio"
    st.caption(f"Data: Strava + Garmin · 2018–2026  \nPowered by {provider_label} + LangGraph")

# ---------------------------------------------------------------------------
# Main — render conversation
# ---------------------------------------------------------------------------
st.title("HealthData Agent")
st.caption("Ask questions about your training data in plain English.")

for msg in st.session_state.history:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(_content_str(msg.content))
    elif isinstance(msg, AIMessage) and _content_str(msg.content).strip():
        with st.chat_message("assistant"):
            st.markdown(_content_str(msg.content).strip())

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
if prompt := st.chat_input("Ask about your training…"):
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.history.append(HumanMessage(content=prompt))

    with st.chat_message("assistant"):
        result = None
        tools_called: list[str] = []

        hit_limit = False
        try:
            with st.status("Thinking…", expanded=True) as status:
                _last_logged_msg_id: str | None = None
                for chunk in agent.stream(
                    {"messages": st.session_state.history},
                    config={"recursion_limit": _RECURSION_LIMIT},
                    stream_mode="values",
                ):
                    result = chunk
                    last_msg = chunk["messages"][-1]
                    if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
                        continue
                    msg_id = getattr(last_msg, "id", None)
                    if msg_id and msg_id == _last_logged_msg_id:
                        continue  # same AIMessage re-emitted by a checkpoint step
                    _last_logged_msg_id = msg_id

                    for tc in last_msg.tool_calls:
                        label = _TOOL_LABELS.get(tc["name"], tc["name"])
                        status.write(label)
                        tools_called.append(label)

                n = len(tools_called)
                status.update(
                    label=f"Used {n} tool{'s' if n != 1 else ''}" if n else "Done",
                    state="complete",
                    expanded=False,
                )
        except GraphRecursionError:
            hit_limit = True
            n = len(tools_called)
            status.update(
                label=f"Tool limit reached after {n} call{'s' if n != 1 else ''}",
                state="error",
                expanded=False,
            )
        except Exception as exc:
            st.error(f"Agent error: {exc}")
            st.session_state.history.pop()
            st.stop()

        if not result or not result.get("messages"):
            st.error("Agent returned no response.")
            st.session_state.history.pop()
            st.stop()

        all_msgs = result["messages"]

        # Isolate messages added this turn (everything after the last HumanMessage).
        # Used to avoid surfacing stale replies from prior turns when the limit fires.
        last_human_idx = max(
            (i for i, m in enumerate(all_msgs) if isinstance(m, HumanMessage)),
            default=-1,
        )
        new_msgs = all_msgs[last_human_idx + 1:] if last_human_idx >= 0 else all_msgs

        # Always search only the current turn's messages. Searching all_msgs on a
        # "clean" finish could return a prior turn's reply if the model stalled
        # mid-generation (context overflow with empty content + finish_reason=stop).
        reply = ""
        for msg in reversed(new_msgs):
            if isinstance(msg, AIMessage):
                candidate = _content_str(msg.content).strip()
                if candidate:
                    reply = candidate
                    break

        if not reply:
            # Surface tool results from this turn so the user sees something useful.
            tool_snippets = []
            for msg in new_msgs:
                if not isinstance(msg, ToolMessage):
                    continue
                try:
                    data = json.loads(msg.content)
                    if isinstance(data, dict) and "_chart_json" in data:
                        tool_snippets.append("*Chart generated.*")
                        continue
                except Exception:
                    data = msg.content
                tool_snippets.append(f"**Tool result:** {str(data)[:600]}")
            reply = "\n\n".join(tool_snippets) if tool_snippets else "*(No response generated.)*"

        if hit_limit:
            reply = (
                "> **Note:** The agent reached its tool-call limit. "
                "The response below covers what was gathered so far.\n\n"
                + reply
            )

        st.markdown(reply)

        # Render any charts produced by generate_chart tool calls
        for i, fig in enumerate(_extract_charts(result.get("messages", []))):
            st.plotly_chart(fig, width='stretch', key=f"chart_new_{i}")

    st.session_state.history = _strip_reasoning(result["messages"])

    # Auto-save after every reply
    save_chat(
        st.session_state.chat_id,
        _title_from_messages(st.session_state.history),
        st.session_state.history,
    )
