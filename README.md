# Agent Arena Submission Agent

A production-shaped Python agent scaffold for [Agent Arena](https://agent-arena.dev) submissions. Built on **Google ADK + Gemini + FastMCP**.

> **This is boilerplate only.** Task-solving logic, real MCP tool names, and the auth-refresh flow are left as clearly-marked TODO stubs.

---

## Quick Start

```bash
cd AgentArena

# 1. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your real GEMINI_API_KEY and MCP_ENDPOINT

# 4. Run
python agent.py
```

---

## Project Structure

```
AgentArena/
├── agent.py                   # Entrypoint: ADK agent setup + poll loop launch
├── config.py                  # Env loading, validation, JWT refresh stub
├── arena_mcp/
│   ├── __init__.py
│   ├── client.py              # MCP client: get_task(), submit_task() with JWT retry
│   └── poll.py                # Poll loop: get → solve → submit, backoff & clean stop
├── content/
│   └── tasks/                 # Output dir: one subfolder per task slug
├── scripts/
│   └── check_secrets.py       # Pre-push secret scanner
├── deploy/
│   ├── Dockerfile             # Python 3.12-slim container
│   └── cloudbuild.yaml        # GCP Cloud Run Job stub (placeholders)
├── .env.example               # All config vars with placeholder values
├── .gitignore
├── requirements.txt
└── README.md                  # ← you are here
```

---

## Key TODOs

| File | Function | What to fill in |
|------|----------|----------------|
| `config.py` | `refresh_jwt()` | Auth endpoint URL + credential exchange flow |
| `arena_mcp/client.py` | `get_task()` | Real MCP tool name, response schema mapping |
| `arena_mcp/client.py` | `submit_task()` | Real MCP tool name, payload format |
| `arena_mcp/poll.py` | `solve_task()` | Your actual task-solving pipeline |
| `deploy/cloudbuild.yaml` | substitutions | GCP project, region, service account |

---

## Stopping the Agent

- **Ctrl-C** — graceful shutdown via `KeyboardInterrupt`
- **Touch `FINISH`** — create a file named `FINISH` in the working directory

---

## Pre-Push Secret Check

```bash
python scripts/check_secrets.py
```

Exits non-zero if potential API keys, JWTs, or secrets are found in tracked files.

---

## License

Private — not for redistribution.
