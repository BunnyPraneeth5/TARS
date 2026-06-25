# TARS – Agent Arena Codebase Guide

> **Audience:** You know Python. You don't want to re-read the source every time you need to change something.

---

## 1. Project Overview

TARS is an autonomous agent that competes in **Agent Arena** — a platform where agents receive tasks, solve them with an LLM, submit answers, and get scored 0-100.

### Full Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                         agent.py main()                         │
│                               │                                 │
│                     asyncio.run(run_loop())                     │
│                               │                                 │
│  ┌───────────── poll.py run_loop() ─────────────────────────┐   │
│  │                                                           │   │
│  │  1. register_agent(agent_id)   ← one-time at startup      │   │
│  │          │                                                 │   │
│  │          ▼                                                 │   │
│  │  ┌──► 2. get_task(agent_id)                               │   │
│  │  │       │                                                 │   │
│  │  │       ├─ None → sleep(30s) → loop back ────────────┐   │   │
│  │  │       │                                             │   │   │
│  │  │       ▼                                             │   │   │
│  │  │   3. solve_task(task)                               │   │   │
│  │  │       │  _build_prompt() → provider pool → LLM     │   │   │
│  │  │       │  write submission to content/tasks/<slug>/  │   │   │
│  │  │       ▼                                             │   │   │
│  │  │   4. submit_task(agent_id, task_id, file_path)      │   │   │
│  │  │       │                                             │   │   │
│  │  │       ▼                                             │   │   │
│  │  │   5. Check score                                    │   │   │
│  │  │       ├─ score ≥ 70 → PASSED → sleep(5s) ──────────┤   │   │
│  │  │       │                                             │   │   │
│  │  │       └─ score < 70 → skip_task() → sleep(5s) ─────┤   │   │
│  │  │                                                     │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                           │   │
│  │  Stop on: FINISH file, Ctrl-C, or unrecoverable error     │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### MCP Communication

All Arena API calls go through **fastmcp.Client** using MCP tool calls (`get_tasks`, `submit_task`, `skip_task`, `register_agent`). Every call sends `idToken` (JWT) and `agentId`. If the server responds with an auth error, the client retries once after calling `config.refresh_jwt()`.

---

## 2. File-by-File Breakdown

---

### `agent.py` (110 lines)

**What it does:** Main entrypoint. Sets up the ADK agent, runner, session service, optionally inits Traceloop, then calls `run_loop()`.

| Function / Object | Lines | Signature | Purpose |
|---|---|---|---|
| `_sanitize_name()` | 49-58 | `(name: str) → str` | Converts `AGENT_NAME` into a Python-identifier-safe string for ADK. Replaces non-alphanumeric chars with `_`. |
| `agent` | 63-73 | `LlmAgent` instance | The ADK agent. Model comes from `config.GEMINI_MODEL`. System instruction is a static string (line 67-72). |
| `runner` | 78-82 | `Runner` instance | ADK Runner wired to the agent. Imported by `poll.py` to call Gemini. |
| `session_service` | 77 | `InMemorySessionService` | In-memory session store. One session is created per task solve in `_solve_with_gemini()`. |
| `main()` | 100-105 | `() → None` | Imports `run_loop` and calls `asyncio.run(run_loop())`. |

**What to edit here if you want to:**
- Change the ADK agent's system instruction → lines 67-72 (the `instruction=` kwarg). **Note:** This instruction is only used by ADK internally; the actual LLM prompt is built in `poll.py:_build_prompt()`.
- Switch the default Gemini model → change `GEMINI_MODEL` in `.env` (the agent reads `config.GEMINI_MODEL` at line 65).
- Disable Traceloop → remove or leave `TRACELOOP_API_KEY` blank in `.env`.

**TODOs:**
- Line 71: `# TODO: Refine this system instruction once you know the typical task shapes.`
- Lines 84-95: Comment block describing how to call the runner from `solve_task()` — this is already implemented in `poll.py:_solve_with_gemini()`, so this comment is stale.

---

### `config.py` (66 lines)

**What it does:** Loads `.env`, validates required vars, and exposes them as module-level constants. Imported first by everything.

| Symbol | Lines | Type | Purpose |
|---|---|---|---|
| `MCP_ENDPOINT` | 18 | `str` | Arena MCP server URL. **Fatal exit** if empty. |
| `LLM_PROVIDER` | 25 | `str` | `"gemini"` or `"nvidia"`. Controls which API key is validated at startup. |
| `GEMINI_API_KEY` | 27 | `str` | Google AI Studio key. Fatal if provider is `gemini` and this is empty. |
| `NVIDIA_API_KEY` | 28 | `str` | NVIDIA key. Fatal if provider is `nvidia` and this is empty. |
| `EPHEMERAL_JWT` | 36 | `str` | JWT for Arena auth. Passed as `idToken` in every MCP call. |
| `TRACELOOP_API_KEY` | 37 | `str` | Optional. Enables Traceloop if set. |
| `AGENT_ID` | 38 | `str` | Agent's unique ID from Arena registration. Default: `"agent-arena-submission"`. |
| `AGENT_NAME` | 39 | `str` | Display name. Default: `"AgentArenaBot"`. |
| `GEMINI_MODEL` | 42 | `str` | Model string for ADK. Default: `"gemini-2.5-flash"`. |
| `NVIDIA_MODEL` | 45 | `str` | Model string for NVIDIA. Default: `"nvidia/nemotron-3-super-120b-a12b"`. |
| `NVIDIA_BASE_URL` | 46 | `str` | NVIDIA API endpoint. Default: `"https://integrate.api.nvidia.com/v1"`. |
| `refresh_jwt()` | 50-65 | `() → str` | **Stub.** Raises `NotImplementedError`. Meant to re-authenticate and update `EPHEMERAL_JWT`. |

**What to edit here if you want to:**
- Add a new env var → add `os.environ.get(...)` line, add validation if required, add to `.env.example`.
- Fix the JWT refresh → implement `refresh_jwt()` at lines 50-65.

**TODOs:**
- Lines 53-57: `refresh_jwt()` is unimplemented. Auth endpoint and credential exchange flow are unknown.

---

### `arena_mcp/client.py` (258 lines)

**What it does:** Thin async wrapper around `fastmcp.Client`. Every function opens a connection, calls an MCP tool, parses the result, and handles auth retries.

| Function / Class | Lines | Signature | Purpose |
|---|---|---|---|
| `TaskPayload` | 24-31 | `@dataclass` | Data container: `task_id`, `slug`, `prompt`, `metadata`. |
| `AuthError` | 36-37 | Exception | Sentinel exception for auth failures. (Defined but never raised directly — `_is_auth_error()` checks existing exceptions instead.) |
| `_build_client()` | 42-44 | `() → Client` | Creates a `fastmcp.Client` pointed at `config.MCP_ENDPOINT`. |
| `_is_auth_error()` | 47-50 | `(exc: Exception) → bool` | Checks if error message contains `auth`, `unauthorized`, `403`, `jwt`, or `token`. |
| `_parse_tool_result()` | 53-80 | `(result: Any) → Any` | Extracts JSON from `CallToolResult.content[0].text`. Falls back to returning raw value. |
| `get_task()` | 85-136 | `(agent_id: str) → TaskPayload \| None` | Calls MCP tool `"get_tasks"`. Sends `idToken` + `agentId`. Parses response into `TaskPayload`. Returns `None` if queue is empty. Retries once on auth error. |
| `submit_task()` | 139-182 | `(agent_id, task_id, file_path) → dict` | Reads submission file, calls MCP tool `"submit_task"` with `content`. Returns response dict (contains `score`). |
| `skip_task()` | 185-221 | `(agent_id, task_id) → dict` | Calls MCP tool `"skip_task"`. Used when score < 70. |
| `register_agent()` | 224-257 | `(agent_id: str) → dict` | Calls MCP tool `"register_agent"` with `idToken` + `agentId`. |

**What to edit here if you want to:**
- Change how tasks are fetched (field names, filtering) → edit `get_task()` lines 110-127, specifically the `task_data.get(...)` chain.
- Change what gets submitted (e.g., add metadata) → edit `_call()` inside `submit_task()` lines 161-173.
- Fix auth retry to actually work → implement `config.refresh_jwt()` in `config.py`.

**Known gap:** `AuthError` (line 36) is declared but never raised. The auth-retry pattern catches generic `Exception` and checks with `_is_auth_error()`. This works but is less precise.

**Known gap:** `register_agent()` here sends `agentId`, but `register_agent.py` (standalone script) sends `name` instead. These use different parameter names for the same MCP tool — see Section 6.

---

### `arena_mcp/poll.py` (482 lines)

**What it does:** The brain of the agent. Contains the main loop, provider pool, prompt builder, LLM backends (Gemini + NVIDIA), and submission logic.

| Function / Class | Lines | Signature | Purpose |
|---|---|---|---|
| **Constants** | 26-33 | — | `BASE_POLL_INTERVAL=5.0`, `IDLE_POLL_INTERVAL=30.0`, `MAX_BACKOFF=120.0`, `PASS_SCORE_THRESHOLD=70`, `FINISH_SIGNAL_FILE=Path("FINISH")`, `CONTENT_DIR=Path("content/tasks")` |
| `Provider` | 41-72 | `@dataclass` | Tracks name, availability, cooldown state. Key methods: `mark_429()`, `check_ready()`, `seconds_until_ready` property. |
| `_provider_pool` | 76-79 | `list[Provider]` | Global pool: `[Provider("gemini"), Provider("nvidia")]`. Order = priority. |
| `_get_ready_provider()` | 82-87 | `() → Provider \| None` | Returns first non-cooldown provider. |
| `_wait_for_any_provider()` | 90-101 | `() → Provider` | Sleeps until soonest provider recovers. |
| `_is_429_error()` | 104-111 | `(exc) → bool` | Detects rate-limit errors by message text or status code attribute. |
| `_build_prompt()` | 116-133 | `(task: TaskPayload) → str` | Builds user prompt from task slug + description. Instructs LLM to return only the answer. |
| `_build_system_prompt()` | 136-144 | `() → str` | Static system prompt. Used by NVIDIA backend directly; Gemini uses ADK's `instruction` instead. |
| `_strip_code_fences()` | 149-161 | `(text: str) → str` | Removes ` ```python ... ``` ` wrappers from LLM output. |
| `_safe_slug()` | 164-168 | `(slug: str) → str` | Strips `< > : " / \ | ? *` from slugs for safe directory names. |
| `_call_gemini_with_retry()` | 173-213 | `(runner_obj, user_id, session_id, message, max_attempts=3) → str` | Calls Gemini via ADK runner. Exponential backoff: 2s, 4s, 8s. |
| `_solve_with_gemini()` | 216-231 | `(prompt: str) → str` | Creates ADK session, calls `_call_gemini_with_retry()`. Imports `runner` and `session_service` from `agent.py`. |
| `_call_nvidia_with_retry()` | 236-279 | `(prompt, system_prompt, max_attempts=3) → str` | Calls NVIDIA via OpenAI-compatible API. Same backoff pattern. Temp=0.2, max_tokens=4096. |
| `_solve_with_nvidia()` | 282-284 | `(prompt, system_prompt) → str` | Thin wrapper around `_call_nvidia_with_retry()`. |
| `solve_task()` | 289-378 | `(task: TaskPayload) → Path` | Orchestrates solving: builds prompt → picks provider → calls LLM → strips fences → writes `content/tasks/<slug>/submission.md`. Handles 429 failover between providers. |
| `run_loop()` | 383-481 | `() → None` | Main poll loop. Registers agent, then loops: get_task → solve_task → submit_task → check score → skip if < 70. Exponential backoff on errors. Stops on `FINISH` file or Ctrl-C. |

**What to edit here if you want to:**
- Change the LLM prompt → `_build_prompt()` lines 116-133 and `_build_system_prompt()` lines 136-144.
- Change the passing threshold → `PASS_SCORE_THRESHOLD` line 29.
- Change poll timing → `BASE_POLL_INTERVAL` (line 26), `IDLE_POLL_INTERVAL` (line 27).
- Add a new LLM provider → see Section 4.
- Change NVIDIA temperature/max_tokens → `_call_nvidia_with_retry()` lines 258-259.
- Change submission file location → `CONTENT_DIR` line 33 and logic in `solve_task()` lines 371-376.

---

### `arena_mcp/__init__.py` (5 lines)

**What it does:** Package init. Re-exports `get_task`, `submit_task`, and `run_loop`.

**Known gap:** Does not re-export `skip_task` or `register_agent` (added later, init not updated).

---

### `discover_tools.py` (27 lines)

**What it does:** Standalone diagnostic script. Connects to `MCP_ENDPOINT`, calls `client.list_tools()`, and prints every tool name, description, and input schema.

**When to use it:** Run `python discover_tools.py` to see what MCP tools the server exposes and what parameters they expect. Useful when the server API changes.

**No functions to call from other modules** — this is a one-shot script.

---

### `register_agent.py` (49 lines)

**What it does:** Standalone script to manually register an agent with the Arena server. Prints the response and tells you what to put in `.env`.

| Detail | Value |
|---|---|
| MCP tool called | `"register_agent"` |
| Parameters sent | `idToken`, `name` (from `AGENT_NAME`) |
| Output | Prints `agentId` and tells you to update `.env` |

**Critical difference from `client.py:register_agent()`:** This script sends `name` (line 31), while `client.py` sends `agentId` (line 244). These are different parameter names. If the server expects `name` for initial registration, use this script. If it expects `agentId`, the `client.py` version at startup will work. See Section 6 for details.

---

### `requirements.txt` (11 lines)

| Package | Purpose |
|---|---|
| `google-adk>=1.0.0` | Google Agent Development Kit — runs the Gemini LLM agent |
| `google-genai>=1.0.0` | Low-level Gemini API types (`Content`, `Part`) |
| `fastmcp>=2.0.0` | MCP client library for tool calls to the Arena server |
| `httpx>=0.27.0` | HTTP client (transitive dep of fastmcp, pinned for safety) |
| `python-dotenv>=1.0.0` | Loads `.env` file |
| `openai>=1.0.0` | OpenAI-compatible client used for NVIDIA API calls |
| `traceloop-sdk>=0.30.0` | Optional observability (comment out if not needed) |

---

### `.env.example` (25 lines)

Covered fully in Section 3 below.

---

## 3. Configuration Reference

Every variable in `.env.example`, what it does, who uses it, and what breaks if it's wrong.

| Variable | Required? | Default | Used In | What Happens If Wrong |
|---|---|---|---|---|
| `MCP_ENDPOINT` | **Yes** | *(none)* | `config.py:18`, `client.py:44` | `sys.exit()` on startup. Every MCP call fails if the URL is bad. |
| `LLM_PROVIDER` | No | `"gemini"` | `config.py:25`, `poll.py:469` | Controls which API key is validated at startup. Also used in error-handling path to mark the right provider on 429. If set to an unknown value, Gemini key won't be validated but Gemini will still be tried first (pool order). |
| `GEMINI_API_KEY` | If provider=gemini | *(none)* | `config.py:27` (validated at 30-31), used implicitly by `google-adk`/`google-genai` via env var `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `sys.exit()` if provider is gemini and key is empty. LLM calls fail with auth errors if the key is invalid. |
| `NVIDIA_API_KEY` | If provider=nvidia | *(none)* | `config.py:28` (validated at 32-33), `poll.py:246` | `sys.exit()` if provider is nvidia and key is empty. OpenAI client throws auth error if invalid. |
| `EPHEMERAL_JWT` | Effectively yes | `""` | `config.py:36`, every `client.py` function | All MCP calls send this as `idToken`. If empty or expired, server returns auth error. Since `refresh_jwt()` is unimplemented, you must manually update `.env` with a fresh JWT. |
| `TRACELOOP_API_KEY` | No | `""` | `agent.py:32-44` | If empty, Traceloop is skipped silently. If set to a bad key, init fails but agent continues (caught exception at line 41). |
| `AGENT_ID` | No | `"agent-arena-submission"` | `config.py:38`, `poll.py:401,415,429,444` | Used in every MCP call. If this doesn't match what the server has registered, tasks won't be fetched. |
| `AGENT_NAME` | No | `"AgentArenaBot"` | `config.py:39`, `agent.py:37,61,80`, `register_agent.py:17` | Display name. Used for Traceloop app name and ADK runner app name. Sanitized for ADK agent name. |
| `GEMINI_MODEL` | No | `"gemini-2.5-flash"` | `config.py:42`, `agent.py:65` | Passed to `LlmAgent(model=...)`. If the model string is invalid, Gemini calls fail. |
| `NVIDIA_MODEL` | No | `"nvidia/nemotron-3-super-120b-a12b"` | `config.py:45`, `poll.py:253` | Passed to `client.chat.completions.create(model=...)`. Invalid model → NVIDIA API error. |
| `NVIDIA_BASE_URL` | No | `"https://integrate.api.nvidia.com/v1"` | `config.py:46`, `poll.py:245` | Base URL for NVIDIA's OpenAI-compatible endpoint. Wrong URL → connection errors. |

---

## 4. Provider System

### How It Works

The agent maintains a **global provider pool** (`poll.py` lines 76-79):

```python
_provider_pool: list[Provider] = [
    Provider(name="gemini"),    # index 0 = highest priority
    Provider(name="nvidia"),    # index 1 = fallback
]
```

When `solve_task()` runs:

1. `_get_ready_provider()` (line 82) iterates the pool in order and returns the first provider whose `check_ready()` is `True`.
2. If both are in cooldown, `_wait_for_any_provider()` (line 90) sleeps until the soonest one recovers.
3. The task is sent to the chosen provider's backend (`_solve_with_gemini` or `_solve_with_nvidia`).
4. If a **429** occurs, `provider.mark_429()` sets `available=False` and records the timestamp. The loop continues to the next provider.
5. If a **non-429 error** occurs, the provider is added to the `tried` set and the loop tries remaining ready providers.

Each `Provider` has:
- `cooldown = 300.0` seconds (5 minutes). After a 429, the provider is unavailable for this duration.
- `mark_429()` — records `time.monotonic()` and sets `available = False`.
- `check_ready()` — returns `True` if `available` or if `cooldown` has elapsed since `last_429`.

### How to Add a Third Provider (e.g., Groq)

**Step 1: Add config variables** in `config.py`:

```python
# After line 46
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL: str = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
```

**Step 2: Add to `.env.example`** and your `.env`:

```
GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

**Step 3: Add provider to pool** in `poll.py` (after line 79):

```python
_provider_pool: list[Provider] = [
    Provider(name="gemini"),
    Provider(name="nvidia"),
    Provider(name="groq"),      # ← add here; position = priority
]
```

**Step 4: Add solve backend** in `poll.py`. Since Groq uses an OpenAI-compatible API, you can reuse the NVIDIA pattern:

```python
async def _solve_with_groq(prompt: str, system_prompt: str) -> str:
    """Solve a task using Groq."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=config.GROQ_BASE_URL,
        api_key=config.GROQ_API_KEY,
    )
    # Reuse the same retry pattern
    last_exc = None
    for attempt in range(1, 4):
        try:
            response = await client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            text = response.choices[0].message.content
            if text:
                return text
            raise RuntimeError("Groq returned an empty response")
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError("Groq failed after 3 attempts") from last_exc
```

**Step 5: Wire into `solve_task()`** — add a branch in the provider dispatch (around line 335):

```python
if provider.name == "nvidia":
    raw_solution = await _solve_with_nvidia(user_prompt, system_prompt)
elif provider.name == "groq":
    raw_solution = await _solve_with_groq(user_prompt, system_prompt)
else:
    raw_solution = await _solve_with_gemini(user_prompt)
```

**Step 6 (optional): Add startup validation** in `config.py` if you want a fatal exit when the key is missing:

```python
if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
    sys.exit("FATAL: GROQ_API_KEY is not set.")
```

---

## 5. How to Change the Prompt

### Where the Prompts Live

There are **two** prompt locations, serving different purposes:

| Prompt | File | Lines | Used By |
|---|---|---|---|
| ADK agent instruction | `agent.py` | 67-72 | Gemini only (passed to `LlmAgent(instruction=...)`) — acts as a persistent system instruction for the ADK session. |
| `_build_prompt()` | `poll.py` | 116-133 | Both providers. This is the **user message** sent to the LLM. Contains the task slug, description, scoring info, and output format rules. |
| `_build_system_prompt()` | `poll.py` | 136-144 | NVIDIA only. Passed as the `system` role message. Gemini uses the ADK instruction instead. |

### Changing the Prompt

**To change how tasks are solved for both providers**, edit `_build_prompt()` in `poll.py` lines 116-133. This function receives a `TaskPayload` and returns the user-facing prompt string.

Current structure:
```
# Task: {task.slug}

## Description
{task.prompt}

## Instructions
Solve the task... score ≥70... only the solution content...
```

**To make it task-type-aware**, inspect `task.metadata` or `task.slug` and branch:

```python
def _build_prompt(task: TaskPayload) -> str:
    base = f"# Task: {task.slug}\n\n## Description\n{task.prompt}\n\n"

    task_type = task.metadata.get("type", "").lower()

    if task_type == "code" or "code" in task.slug.lower():
        instructions = (
            "Write working code that solves the problem. "
            "Return ONLY the code, no explanations. "
            "Use Python unless the task specifies another language."
        )
    elif task_type == "writing":
        instructions = (
            "Write a clear, well-structured response. "
            "Match the requested format exactly."
        )
    else:
        instructions = (
            "Solve the task. Return ONLY the solution content. "
            "No explanations, no markdown fences unless required."
        )

    return base + f"## Instructions\n{instructions}\n"
```

**To change the system prompt for NVIDIA**, edit `_build_system_prompt()` at lines 136-144.

**To change the system prompt for Gemini**, edit the `instruction=` kwarg in `agent.py` lines 67-72. Note that the ADK agent instruction is set once at module load time, so changing it requires restarting the agent.

---

## 6. Common Failure Modes and Fixes

### AUTH_ERROR on MCP calls

**Symptom:** Log says `AUTH_ERROR on get_task – refreshing JWT and retrying once.` followed by `NotImplementedError: TODO: refresh_jwt()`.

**Root cause:** `EPHEMERAL_JWT` in `.env` has expired. `config.refresh_jwt()` at `config.py:50-65` is a stub.

**Fix:**
1. Get a fresh JWT from the Arena dashboard / auth endpoint.
2. Update `EPHEMERAL_JWT` in `.env`.
3. Restart the agent.

**Long-term fix:** Implement `refresh_jwt()` in `config.py` lines 50-65 once you know the auth endpoint.

---

### 429 Rate Limits

**Symptom:** Log says `Provider gemini hit 429 – cooling down for 300s`.

**What happens:** The provider is marked unavailable for 5 minutes (`Provider.cooldown = 300.0`). The agent tries the next provider in the pool. If all providers are in cooldown, it sleeps until the soonest one recovers.

**Fixes:**
- Reduce request frequency: increase `BASE_POLL_INTERVAL` (line 26) or increase `IDLE_POLL_INTERVAL` (line 27).
- Reduce cooldown: change `Provider.cooldown` (line 48), but be careful not to hit the limit again immediately.
- Add more providers: see Section 4.
- Use a model with higher rate limits (e.g., `gemini-2.0-flash` instead of `gemini-2.5-flash`).

---

### Score < 70 — Task Skipped

**Symptom:** Log says `Score 45 < 70 for task abc123 – skipping to unlock next task`.

**What happens:** `run_loop()` calls `skip_task()` (line 444) to unlock the next task. The low-scoring submission is still saved in `content/tasks/<slug>/submission.md`.

**Fixes:**
- Improve the prompt: edit `_build_prompt()` — see Section 5.
- Lower the threshold: change `PASS_SCORE_THRESHOLD` at line 29 (not recommended for actual competition).
- Add retry logic: before skipping, retry the same task with a modified prompt. Currently not implemented.
- Inspect the submission: check `content/tasks/<slug>/submission.md` to see what the LLM produced.

---

### register_agent Parameter Mismatch

**Symptom:** `register_agent.py` works but `client.py:register_agent()` doesn't (or vice versa), because they send different parameters.

**Root cause:**
- `register_agent.py` line 30-31 sends: `{"idToken": ..., "name": agent_name}`
- `client.py` line 243-245 sends: `{"idToken": ..., "agentId": agent_id}`

The MCP tool may expect `name` for initial registration and `agentId` for subsequent calls, or it may expect one or the other consistently.

**Fix:** Run `python discover_tools.py` to check the actual `register_agent` input schema. Then update whichever file has the wrong parameter name.

---

### solve_task TODO / NotImplementedError

**Symptom:** Log says `solve_task() is not implemented yet!` and the agent crashes.

**Root cause:** This error is from the `except NotImplementedError` handler at `poll.py` line 454-460. It fires if `solve_task()` raises `NotImplementedError`. This was a guardrail from when `solve_task` was a stub.

**Current status:** `solve_task()` is fully implemented (lines 289-378). This error should no longer trigger. If it does, it means one of the functions inside `solve_task()` is raising `NotImplementedError` — most likely `config.refresh_jwt()` being called during an auth retry inside a solve step.

---

### Gemini Returns Empty Response

**Symptom:** `RuntimeError: Gemini returned an empty response` after 3 attempts.

**Root cause:** The ADK runner returned events but none had `is_final_response()` with text content, or the model returned an empty string.

**Fixes:**
- Check that `GEMINI_MODEL` is a valid model identifier.
- Check that `GEMINI_API_KEY` is valid and has quota.
- Increase `max_attempts` in `_call_gemini_with_retry()` (line 178, default 3).
- Try a different model: change `GEMINI_MODEL` in `.env`.

---

### Connection Errors to MCP Server

**Symptom:** `httpx.ConnectError` or similar when calling `get_task()`.

**Fix:** Check that `MCP_ENDPOINT` in `.env` is correct and the server is running. The agent will retry with exponential backoff (line 464), capped at `MAX_BACKOFF=120s`.

---

## 7. Quick Reference Cheat Sheet

| I want to... | File | Location |
|---|---|---|
| **Change the LLM model** | `.env` | `GEMINI_MODEL` or `NVIDIA_MODEL` |
| **Change the task-solving prompt** | `poll.py` | `_build_prompt()` lines 116-133 |
| **Change the system prompt (NVIDIA)** | `poll.py` | `_build_system_prompt()` lines 136-144 |
| **Change the system prompt (Gemini/ADK)** | `agent.py` | `instruction=` kwarg, lines 67-72 |
| **Change the passing score threshold** | `poll.py` | `PASS_SCORE_THRESHOLD` line 29 |
| **Change poll intervals** | `poll.py` | `BASE_POLL_INTERVAL` line 26, `IDLE_POLL_INTERVAL` line 27 |
| **Change 429 cooldown duration** | `poll.py` | `Provider.cooldown` line 48 (default 300s) |
| **Add a new LLM provider** | `config.py` + `poll.py` | See Section 4 (5 steps) |
| **Change NVIDIA temperature** | `poll.py` | `_call_nvidia_with_retry()` line 258 |
| **Change NVIDIA max_tokens** | `poll.py` | `_call_nvidia_with_retry()` line 259 |
| **Change Gemini retry count** | `poll.py` | `_call_gemini_with_retry()` `max_attempts` param, line 178 |
| **Change submission output directory** | `poll.py` | `CONTENT_DIR` line 33 |
| **Stop the agent gracefully** | filesystem | Create a file named `FINISH` in the working directory |
| **Update the JWT** | `.env` | `EPHEMERAL_JWT` — then restart the agent |
| **Implement JWT auto-refresh** | `config.py` | `refresh_jwt()` lines 50-65 |
| **See what MCP tools exist** | terminal | `python discover_tools.py` |
| **Register agent manually** | terminal | `python register_agent.py` |
| **Check register_agent params** | terminal | `python discover_tools.py` → look at `register_agent` schema |
| **Change the agent display name** | `.env` | `AGENT_NAME` |
| **Disable Traceloop** | `.env` | Remove or blank out `TRACELOOP_API_KEY` |
| **Inspect a failed submission** | filesystem | `content/tasks/<slug>/submission.md` |
| **Change code fence stripping** | `poll.py` | `_strip_code_fences()` lines 149-161 |
