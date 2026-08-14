# TARS — Autonomous AI Problem-Solving Agent

TARS is an **autonomous, self-healing AI problem-solving agent** designed to compete on **[Agent Arena](https://agent-arena.dev)** and benchmark platforms via **Model Context Protocol (MCP)**.

It features multi-provider rate-limit failover (**Google Gemini** + **NVIDIA Nemotron**), domain-aware task classification, pre-submission quality assurance, and real-time telemetry tracking.

---

## 📚 Documentation & Guides

- **[User & Beginner Guide](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/USER_GUIDE.md)** — **Start here!** Plain-English explanation of why TARS exists, how it works step-by-step, and who benefits.
- **[Codebase Guide](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/CODEBASE_GUIDE.md)** — In-depth developer guide to every module, data flow, and file relationship.
- **[Provider Extension Guide](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/PROVIDER_GUIDE.md)** — How to add new LLM providers (Groq, Anthropic, Ollama).
- **[Architecture & Future Roadmap](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/FUTURE_UPDATES.md)** — Long-term engineering roadmap and milestone progress.

---

## ⚡ Quick Start

```bash
cd AgentArena

# 1. Activate virtual environment
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# 2. Configure environment variables in .env
# (Ensure GEMINI_API_KEY, NVIDIA_API_KEY, MCP_ENDPOINT, and EPHEMERAL_JWT are set)

# 3. Run the Agent
python agent.py
```

---

## 🏗️ Architecture Overview

```
AgentArena/
├── agent.py                   # Main entrypoint: Initializes providers, solver, & poll loop
├── config.py                  # Env validation & hot-reload JWT refresh
├── providers/                 # LLM Provider Abstraction Layer
│   ├── base.py                # AbstractProvider ABC & 429 rate-limit cooldown
│   ├── registry.py            # ProviderRegistry priority pool & failover engine
│   ├── retry.py               # Shared exponential backoff utility
│   ├── gemini.py              # Google Gemini ADK provider implementation
│   └── nvidia.py              # NVIDIA Nemotron OpenAI-compatible implementation
├── prompts/                   # Task Classifier & Prompt Builder Layer
│   ├── classifier.py          # Domain classifier (CODE, WRITING, MATH, ANALYSIS)
│   ├── builder.py             # PromptBuilder rendering domain-specific guidelines
│   └── templates/             # Per-domain prompt templates (code.py, writing.py, default.py)
├── models/                    # Model Registry & Capabilities Catalog
│   ├── config.py              # ModelConfig dataclass (context windows, pricing)
│   ├── registry.py            # ModelRegistry query engine
│   └── models.yaml            # Declarative YAML catalog
├── core/                      # Core Pipeline Engine
│   ├── solver.py              # Solver orchestrator
│   ├── reviewer.py            # Reviewer agent filtering AI refusals & format flaws
│   └── types.py               # SolveStrategy & Solution data contracts
├── metrics/                   # Telemetry & Performance Engine
│   ├── collector.py           # MetricsCollector in-memory engine
│   └── exporters.py           # JSON snapshot exporter (tars_metrics.json)
├── arena_mcp/                 # Agent Arena MCP Adapter
│   ├── client.py              # MCP client wrappers (get_task, submit_task, skip_task)
│   └── poll.py                # Main polling loop execution
├── content/tasks/             # Saved submissions (content/tasks/<slug>/submission.md)
└── scripts/
    └── check_secrets.py       # Pre-push secret scanner
```

---

## 🛠️ Common Commands

| Task | Command |
|---|---|
| **Start Agent Polling Loop** | `python agent.py` |
| **Register Agent Manually** | `python register_agent.py` |
| **Discover Server MCP Tools** | `python discover_tools.py` |
| **Scan Repo for Secrets** | `python scripts/check_secrets.py` |
| **Graceful Shutdown** | Create a file named `FINISH` in the working directory |

---

## 🛡️ License

Private — for internal research and competition development.
