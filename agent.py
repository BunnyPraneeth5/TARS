"""
agent.py – Main entrypoint for the Agent Arena submission agent.

Sets up the ADK LlmAgent + Runner + InMemorySessionService,
optionally initialises Traceloop, then delegates to the poll loop.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys

import config  # must import first – validates env vars on load

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Traceloop (optional) ───────────────────────────────────────────────────

if config.TRACELOOP_API_KEY:
    try:
        from traceloop.sdk import Traceloop

        Traceloop.init(
            app_name=config.AGENT_NAME,
            api_key=config.TRACELOOP_API_KEY,
        )
        logger.info("Traceloop initialised (app=%s)", config.AGENT_NAME)
    except Exception:
        logger.warning("Traceloop init failed – continuing without tracing.", exc_info=True)
else:
    logger.debug("TRACELOOP_API_KEY not set – skipping Traceloop init.")


# ── ADK Agent setup ────────────────────────────────────────────────────────

def _sanitize_name(name: str) -> str:
    """Turn an arbitrary AGENT_NAME into a valid Python-style identifier.

    ADK agent names must be identifier-safe (letters, digits, underscores,
    cannot start with a digit).
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"a_{sanitized}"
    return sanitized or "arena_agent"


agent_name = _sanitize_name(config.AGENT_NAME)

agent = LlmAgent(
    name=agent_name,
    model=config.GEMINI_MODEL,
    description="Agent Arena submission agent – solves tasks via MCP.",
    instruction=(
        "You are an expert problem solver competing in Agent Arena. "
        "Analyze the given task details (code, math, writing, analysis) "
        "and produce precise, high-scoring solutions that follow format rules exactly."
    ),
)

# ── Runner + Session ────────────────────────────────────────────────────────

session_service = InMemorySessionService()
runner = Runner(
    agent=agent,
    app_name=config.AGENT_NAME,
    session_service=session_service,
)


# ── Entrypoint ──────────────────────────────────────────────────────────────

def main() -> None:
    """Start the polling loop with configured providers, solver, and metrics engine."""
    from arena_mcp.poll import run_loop
    from core import Reviewer, Solver
    from metrics import MetricsCollector
    from models import ModelRegistry
    from providers import GeminiProvider, NVIDIAProvider, ProviderRegistry

    model_registry = ModelRegistry()
    registry = ProviderRegistry([
        GeminiProvider(runner=runner, session_service=session_service),
        NVIDIAProvider(),
    ])
    metrics = MetricsCollector()
    reviewer = Reviewer()
    solver = Solver(
        provider_registry=registry,
        reviewer=reviewer,
        metrics_collector=metrics,
    )

    logger.info("🚀  Starting Agent Arena agent (%s / %s)", config.AGENT_ID, agent_name)
    asyncio.run(run_loop(solver=solver, metrics=metrics))



if __name__ == "__main__":
    main()

