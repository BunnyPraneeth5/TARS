"""
config.py – All environment / configuration loading lives here.

Reads from .env via python-dotenv, validates required keys,
and exposes them as module-level constants.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()  # picks up .env in project root (or parent dirs)

# ── Required ────────────────────────────────────────────────────────────────
MCP_ENDPOINT: str = os.environ.get("MCP_ENDPOINT", "")

if not MCP_ENDPOINT:
    sys.exit("FATAL: MCP_ENDPOINT is not set. Add it to .env or export it.")

# ── LLM provider selection ──────────────────────────────────────────────────
# "gemini" (default) or "nvidia"
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "gemini").lower()

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "")

if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    sys.exit("FATAL: GEMINI_API_KEY is not set. Add it to .env or export it.")
if LLM_PROVIDER == "nvidia" and not NVIDIA_API_KEY:
    sys.exit("FATAL: NVIDIA_API_KEY is not set. Add it to .env or export it.")

# ── Optional / with defaults ────────────────────────────────────────────────
EPHEMERAL_JWT: str = os.environ.get("EPHEMERAL_JWT", "")
TRACELOOP_API_KEY: str = os.environ.get("TRACELOOP_API_KEY", "")
AGENT_ID: str = os.environ.get("AGENT_ID", "agent-arena-submission")
AGENT_NAME: str = os.environ.get("AGENT_NAME", "AgentArenaBot")

# Gemini model identifier used by ADK
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# NVIDIA model identifier
NVIDIA_MODEL: str = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")
NVIDIA_BASE_URL: str = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")


# ── JWT refresh stub ────────────────────────────────────────────────────────
def refresh_jwt() -> str:
    """Re-authenticate with the Arena auth endpoint and return a fresh JWT.

    TODO: Implement once the Arena auth docs are available.
      1. POST to the auth endpoint (unknown URL) with agent credentials.
      2. Parse the response for a new ephemeral JWT.
      3. Update the module-level EPHEMERAL_JWT so subsequent MCP calls use it.
      4. Persist the new JWT to .env or an in-memory store as needed.

    Raises:
        NotImplementedError: Always, until the real auth flow is wired up.
    """
    raise NotImplementedError(
        "TODO: refresh_jwt() – fill in once you know the Arena auth endpoint "
        "and credential exchange flow."
    )
