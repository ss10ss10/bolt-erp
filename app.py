"""ERP Multiagent Chatbot — Streamlit entry point.

Run with:
    streamlit run app.py
"""

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment & path setup (must happen before local imports)
# ---------------------------------------------------------------------------
load_dotenv()

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.logging_config import setup as setup_logging  # noqa: E402

setup_logging()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local imports (after path & logging are set up)
# ---------------------------------------------------------------------------
from agents import Runner  # noqa: E402  (openai-agents SDK)

from context import ERPContext  # noqa: E402
from erp_agents import build_intent_router  # noqa: E402
from tools.data_loader import available_tables  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ERP Chatbot",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_agent" not in st.session_state:
    st.session_state.active_agent = "—"

if "router" not in st.session_state:
    logger.info("=" * 60)
    logger.info("ERP Chatbot starting up — initialising agent network")
    logger.info("=" * 60)
    with st.spinner("Initialising agents…"):
        st.session_state.router = build_intent_router()
    logger.info("Agent network ready — app is live")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _render_response(payload: dict, key_prefix: str) -> None:
    """Render a stored assistant response dict (text + tables + charts).

    key_prefix must be unique per call site so Streamlit never sees two
    elements with the same auto-generated ID.
    """
    if payload.get("text"):
        st.markdown(payload["text"])
    for t_idx, tbl in enumerate(payload.get("tables", [])):
        st.subheader(tbl["title"])
        st.dataframe(tbl["df"], key=f"{key_prefix}_tbl_{t_idx}", width="stretch")
    for c_idx, fig in enumerate(payload.get("charts", [])):
        st.plotly_chart(fig, key=f"{key_prefix}_chart_{c_idx}", width="stretch")


# ---------------------------------------------------------------------------
# Async runner
# ---------------------------------------------------------------------------
def run_agent(query: str) -> tuple[str, ERPContext]:
    ctx = ERPContext()

    async def _run():
        return await Runner.run(
            st.session_state.router,
            query,
            context=ctx,
            max_turns=15,
        )

    logger.info("─" * 60)
    logger.info("USER QUERY  →  %s", query)
    logger.info("─" * 60)

    t0 = time.perf_counter()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
    finally:
        loop.close()

    elapsed = time.perf_counter() - t0
    active = getattr(result.last_agent, "name", "Unknown Agent")
    ctx.active_agent = active

    logger.info(
        "RESPONSE  ←  agent=%r  tables=%d  charts=%d  elapsed=%.2fs",
        active, len(ctx.tables), len(ctx.charts), elapsed,
    )
    for t in ctx.tables:
        logger.debug("  table: %r  (%d rows)", t["title"], len(t["df"]))
    for i, fig in enumerate(ctx.charts):
        logger.debug("  chart[%d]: %r", i, fig.layout.title.text if fig.layout.title else "untitled")

    return str(result.final_output), ctx


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🏭 ERP Chatbot")
    st.caption("Powered by OpenAI Agents SDK")

    st.divider()

    st.subheader("Last active agent")
    agent_placeholder = st.empty()
    agent_placeholder.info(st.session_state.active_agent)

    st.divider()

    st.subheader("Loaded data tables")
    tables = available_tables()
    if tables:
        for t in tables:
            st.write(f"• `{t}`")
    else:
        st.warning("No CSV files in `data/` yet.\nPaste your generated CSVs there and restart.")

    st.divider()

    st.subheader("Sample queries")
    examples = [
        "Give me an executive dashboard",
        "Show total revenue by month",
        "Which customers have the highest revenue?",
        "Are there any low stock alerts?",
        "Show delivery performance by carrier",
        "What are our overdue invoices?",
        "Give me a production quality report",
        "Compare revenue vs procurement spend",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex[:20]}"):
            st.session_state._inject_query = ex
            logger.debug("Sidebar shortcut clicked: %r", ex)

    if st.button("🗑️ Clear conversation", use_container_width=True):
        logger.info("Conversation cleared by user")
        st.session_state.messages = []
        st.session_state.active_agent = "—"
        st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("ERP Assistant")
st.caption("Ask anything about your business data — sales, inventory, finance, logistics, manufacturing, and more.")

# Render chat history — each message gets a unique prefix based on its index
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if isinstance(content, str):
            st.markdown(content)
        else:
            _render_response(content, key_prefix=f"hist_{msg_idx}")

# Handle sidebar example button injections
injected = st.session_state.pop("_inject_query", None)

# Chat input
user_input = st.chat_input("Ask about your ERP data…") or injected

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                text, ctx = run_agent(user_input)
            except Exception as exc:
                logger.error("Agent run failed: %s", exc, exc_info=True)
                error_msg = f"**Error:** {exc}\n\nPlease check your `OPENAI_API_KEY` in `.env`."
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.stop()

        st.session_state.active_agent = ctx.active_agent
        agent_placeholder.info(ctx.active_agent)

        # Use a fresh unique prefix for the live response so it never
        # collides with any history render prefix.
        live_prefix = f"live_{uuid.uuid4().hex[:8]}"
        payload = {
            "text": text,
            "tables": [{"title": t["title"], "df": t["df"]} for t in ctx.tables],
            "charts": ctx.charts,
        }
        _render_response(payload, key_prefix=live_prefix)

    st.session_state.messages.append({"role": "assistant", "content": payload})
