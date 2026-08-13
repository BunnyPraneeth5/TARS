# Phase 1: Foundation — Implementation Plan

> **Scope:** Milestone 1 (Provider Abstraction) + Milestone 4 (Task Classifier) + 3 Bug Fixes  
> **Source:** [FUTURE_UPDATES.md](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/FUTURE_UPDATES.md) — Phase 1 (Lines 1753–1758)  
> **Estimated Effort:** ~5–7 days

---

## User Review Required

> [!IMPORTANT]
> **Zero-downtime constraint:** Every step maintains a working agent. The `poll.py` → provider migration will be done so that `python agent.py` works identically before and after each commit-sized change.

> [!WARNING]
> **`refresh_jwt()` implementation:** The FUTURE_UPDATES doc notes the auth endpoint URL is unknown. The plan implements a *graceful degradation* pattern (catch `NotImplementedError`, log, re-raise the original auth error) rather than a real HTTP-based refresh. If you know the actual auth endpoint, please share it so we can implement a real refresh.

> [!IMPORTANT]
> **`register_agent` parameter mismatch:** The standalone [register_agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/register_agent.py) sends `name`, while [client.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/client.py) sends `agentId`. The plan unifies both to send **both** `agentId` **and** `name` so the server gets whatever it needs. If you know which the server actually expects, let me know.

---

## Open Questions

> [!IMPORTANT]
> **Groq provider addition:** The roadmap mentions Groq as a high-priority future provider. Should I add a `GroqProvider` stub as part of this Phase 1 work to validate the abstraction, or leave it for later?

---

## Proposed Changes

The work is organized into **5 workstreams** executed sequentially. Each produces a working agent.

---

### Workstream 1: Bug Fixes (3 quick wins)

These are small, isolated fixes called out explicitly in Phase 1.

#### [MODIFY] [__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/__init__.py)
- Add missing re-exports: `skip_task`, `register_agent` from `client.py`
- Add `solve_task` from `poll.py`
- Currently only exports `get_task`, `submit_task`, `run_loop`

#### [MODIFY] [config.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/config.py)
- Replace `refresh_jwt()` stub that raises `NotImplementedError` with a graceful implementation:
  - Attempt to read a fresh JWT from the `.env` file (covers the case where a user manually updates it during a run)
  - If the JWT hasn't changed, log a clear error message with instructions
  - Update the module-level `EPHEMERAL_JWT` in-memory so subsequent calls use the new value
  - This unblocks the auth-retry paths in `client.py` that currently crash on `NotImplementedError`

#### [MODIFY] [register_agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/register_agent.py)
- Change `"name": agent_name` → send both `"agentId"` and `"name"` to cover both server expectations
- Align parameter names with `client.py:register_agent()` for consistency

---

### Workstream 2: Provider Abstraction (Milestone 1)

This is the core refactor — extracting all provider logic from [poll.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py) (337 of its 482 lines) into a clean module structure.

#### [NEW] `providers/` package structure
```
providers/
├── __init__.py          # Re-exports: AbstractProvider, ProviderRegistry
├── base.py              # AbstractProvider ABC + Provider health state
├── registry.py          # ProviderRegistry: pool management, selection, cooldown
├── retry.py             # Shared retry-with-backoff utility (async decorator)
├── gemini.py            # GeminiProvider(AbstractProvider)
└── nvidia.py            # NVIDIAProvider(AbstractProvider)
```

#### [NEW] [base.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/base.py)
- `AbstractProvider` ABC with:
  - `name: str` — provider identifier
  - `available: bool` — cooldown tracking (migrated from `Provider` dataclass)
  - `last_429: float` — timestamp tracking
  - `cooldown: float = 300.0` — cooldown duration
  - `async solve(prompt: str, system_prompt: str) -> str` — abstract method
  - `mark_rate_limited() -> None` — marks 429 (migrated from `Provider.mark_429()`)
  - `check_ready() -> bool` — checks cooldown (migrated from `Provider.check_ready()`)
  - `seconds_until_ready: float` — property (migrated from `Provider.seconds_until_ready`)
  - `is_429_error(exc: Exception) -> bool` — static method (migrated from `_is_429_error()`)

#### [NEW] [registry.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/registry.py)
- `ProviderRegistry` class:
  - `register(provider: AbstractProvider) -> None` — add provider to pool
  - `get_ready() -> AbstractProvider | None` — replaces `_get_ready_provider()`
  - `async wait_for_any() -> AbstractProvider` — replaces `_wait_for_any_provider()`
  - `get_all() -> list[AbstractProvider]` — list all registered providers
  - Internally maintains the ordered list (priority = registration order)

#### [NEW] [retry.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/retry.py)
- `async def call_with_retry(fn, max_attempts=3, base_delay=2.0) -> str`
  - Unified retry logic replacing both `_call_gemini_with_retry()` and `_call_nvidia_with_retry()`
  - Exponential backoff: `base_delay * 2^attempt`
  - Logs attempt/failure/success
  - Returns the result or raises after max attempts

#### [NEW] [gemini.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/gemini.py)
- `GeminiProvider(AbstractProvider)`:
  - Constructor takes `runner` and `session_service` as arguments (breaks the circular import with `agent.py`)
  - `solve()` creates an ADK session, builds a `Content` message, calls the runner via `call_with_retry()`
  - Migrated from `_solve_with_gemini()` and `_call_gemini_with_retry()` in [poll.py:173–231](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py#L173-L231)

#### [NEW] [nvidia.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/nvidia.py)
- `NVIDIAProvider(AbstractProvider)`:
  - Constructor takes `api_key`, `model`, `base_url` from config
  - `solve()` calls the OpenAI-compatible API via `call_with_retry()`
  - Migrated from `_solve_with_nvidia()` and `_call_nvidia_with_retry()` in [poll.py:236–284](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py#L236-L284)

#### [NEW] [providers/__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/__init__.py)
- Re-exports: `AbstractProvider`, `ProviderRegistry`, `GeminiProvider`, `NVIDIAProvider`

#### [MODIFY] [poll.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py)
- **Remove** (337 lines):
  - `Provider` dataclass (lines 41–72)
  - `_provider_pool` global (lines 76–79)
  - `_get_ready_provider()` (lines 82–87)
  - `_wait_for_any_provider()` (lines 90–101)
  - `_is_429_error()` (lines 104–111)
  - `_call_gemini_with_retry()` (lines 173–213)
  - `_solve_with_gemini()` (lines 216–231)
  - `_call_nvidia_with_retry()` (lines 236–279)
  - `_solve_with_nvidia()` (lines 282–284)
- **Rewrite** `solve_task()`:
  - Accept a `ProviderRegistry` (or import a module-level singleton)
  - Use `registry.get_ready()` / `registry.wait_for_any()` instead of the removed functions
  - Call `provider.solve(prompt, system_prompt)` instead of the if/elif dispatch
  - Keep prompt building, code fence stripping, file writing unchanged
- **Rewrite** `run_loop()`:
  - Build the `ProviderRegistry` at startup, register `GeminiProvider` and `NVIDIAProvider`
  - Pass the registry to `solve_task()`
  - Remove the 429-in-outer-loop handler that used `config.LLM_PROVIDER` (lines 467–473) — 429s are now handled inside `solve_task()` via the registry

#### [MODIFY] [agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/agent.py)
- Remove the stale TODO comment block (lines 84–95)
- The `runner` and `session_service` remain here but are now passed to `GeminiProvider()` constructor in `poll.py:run_loop()` instead of being imported inside a function body — **breaking the circular import**

---

### Workstream 3: Task Classifier (Milestone 4)

A rule-based classifier that detects task types from slug/prompt keywords and routes to type-specific prompt templates.

#### [NEW] `prompts/` package structure
```
prompts/
├── __init__.py          # Re-exports: TaskClassifier, PromptBuilder
├── classifier.py        # TaskClassifier: rule-based classification
├── builder.py           # PromptBuilder: template selection + rendering
└── templates/
    ├── __init__.py
    ├── code.py          # Code task prompt template
    ├── writing.py       # Writing/analysis task prompt template
    └── default.py       # Generic fallback (identical to current _build_prompt)
```

#### [NEW] [classifier.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/classifier.py)
- `TaskType` enum: `CODE`, `WRITING`, `MATH`, `ANALYSIS`, `DEFAULT`
- `TaskClassifier` class:
  - `classify(task: TaskPayload) -> TaskType`
  - Rule-based detection using slug keywords, metadata fields, and prompt content patterns
  - Classification rules:
    - `CODE` — slug/prompt contains: python, javascript, js, code, function, algorithm, bigcodebench, implement, debug, memory leak, NL2SQL
    - `WRITING` — slug/prompt contains: write, essay, article, blog, creative, documentation
    - `MATH` — slug/prompt contains: math, calculate, equation, prove, formula
    - `ANALYSIS` — slug/prompt contains: analyze, architecture, scalability, design, evaluate, blockchain, forensics
    - `DEFAULT` — fallback for everything else
  - Logs the classification decision for debugging

#### [NEW] [builder.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/builder.py)
- `PromptBuilder` class:
  - `build_prompt(task: TaskPayload, task_type: TaskType) -> str`
  - `build_system_prompt(task_type: TaskType) -> str`
  - Selects the appropriate template based on `TaskType`
  - The `DEFAULT` template produces **identical output** to the current `_build_prompt()` and `_build_system_prompt()` in poll.py

#### [NEW] Template files (`code.py`, `writing.py`, `default.py`)
- Each template module exports:
  - `USER_PROMPT_TEMPLATE: str` — the user prompt format string
  - `SYSTEM_PROMPT: str` — the system prompt for this task type
- `code.py`: Emphasizes working code, correct output format, language detection, no explanations
- `writing.py`: Emphasizes clarity, structure, format matching, tone
- `default.py`: Exact copy of current `_build_prompt()` / `_build_system_prompt()` output

#### [MODIFY] [poll.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py)
- **Remove**: `_build_prompt()` and `_build_system_prompt()` functions
- **Add** in `solve_task()`:
  - Instantiate `TaskClassifier` and `PromptBuilder`
  - `task_type = classifier.classify(task)`
  - `user_prompt = builder.build_prompt(task, task_type)`
  - `system_prompt = builder.build_system_prompt(task_type)`
  - Log the classification: `logger.info("Task %s classified as %s", task.slug, task_type.name)`

---

### Workstream 4: Agent.py Cleanup

#### [MODIFY] [agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/agent.py)
- Remove stale TODO comment block (lines 84–95) about how to call the runner — this is now handled by `GeminiProvider`
- Update the ADK agent `instruction` to be more refined (task-type-aware reference, per the TODO at line 71)

---

### Workstream 5: Documentation

#### [NEW] [docs/PROVIDER_GUIDE.md](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/PROVIDER_GUIDE.md)
- How to add a new provider (implement `AbstractProvider`, register in `run_loop()`)
- Provider interface contract
- Configuration requirements
- Rate limit handling

---

## File Change Summary

| Action | File | Workstream |
|--------|------|------------|
| MODIFY | [__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/__init__.py) | 1: Bug fixes |
| MODIFY | [config.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/config.py) | 1: Bug fixes |
| MODIFY | [register_agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/register_agent.py) | 1: Bug fixes |
| NEW | [providers/__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/__init__.py) | 2: Provider Abstraction |
| NEW | [providers/base.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/base.py) | 2: Provider Abstraction |
| NEW | [providers/registry.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/registry.py) | 2: Provider Abstraction |
| NEW | [providers/retry.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/retry.py) | 2: Provider Abstraction |
| NEW | [providers/gemini.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/gemini.py) | 2: Provider Abstraction |
| NEW | [providers/nvidia.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/providers/nvidia.py) | 2: Provider Abstraction |
| MODIFY | [poll.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/arena_mcp/poll.py) | 2 + 3 |
| MODIFY | [agent.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/agent.py) | 2 + 4 |
| NEW | [prompts/__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/__init__.py) | 3: Task Classifier |
| NEW | [prompts/classifier.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/classifier.py) | 3: Task Classifier |
| NEW | [prompts/builder.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/builder.py) | 3: Task Classifier |
| NEW | [prompts/templates/__init__.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/templates/__init__.py) | 3: Task Classifier |
| NEW | [prompts/templates/code.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/templates/code.py) | 3: Task Classifier |
| NEW | [prompts/templates/writing.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/templates/writing.py) | 3: Task Classifier |
| NEW | [prompts/templates/default.py](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/prompts/templates/default.py) | 3: Task Classifier |
| NEW | [docs/PROVIDER_GUIDE.md](file:///c:/Users/karup/projects/Agent-Dev/AgentArena/docs/PROVIDER_GUIDE.md) | 5: Docs |

**Total: 7 modified files, 13 new files**

---

## Verification Plan

### Manual Verification
- Run `python agent.py` and verify the agent starts, registers, polls, solves, and submits identically to before
- Verify logs show task classification decisions
- Verify the provider abstraction is being used (log messages from `GeminiProvider` / `NVIDIAProvider`)

### Smoke Tests
- Import `providers` package and verify `AbstractProvider`, `ProviderRegistry` are importable
- Import `prompts` package and verify `TaskClassifier`, `PromptBuilder` are importable
- Verify `PromptBuilder` with `TaskType.DEFAULT` produces **identical** output to the old `_build_prompt()` / `_build_system_prompt()`
- Verify `__init__.py` re-exports include `skip_task`, `register_agent`
- Verify `config.refresh_jwt()` no longer raises `NotImplementedError`

### Regression Check
- Verify `poll.py` has zero provider-specific logic (no `_solve_with_gemini`, `_solve_with_nvidia`, `Provider` dataclass)
- Verify `poll.py` has zero prompt-building logic (no `_build_prompt`, `_build_system_prompt`)
- Verify no circular imports exist (the `from agent import runner` deferred import is eliminated)
