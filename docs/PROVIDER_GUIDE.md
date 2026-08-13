# TARS – LLM Provider Guide

This guide explains how LLM providers are structured, managed, and extended in the TARS framework.

---

## 1. Overview

TARS decouples task execution from specific LLM providers using an abstract provider interface (`AbstractProvider`) and a registry pattern (`ProviderRegistry`).

```
┌────────────────────────────────────────────────────────────────┐
│                         ProviderRegistry                       │
│                                                                │
│  [ Priority 1 ]           [ Priority 2 ]         [ Priority N ]│
│  GeminiProvider     --->  NVIDIAProvider   --->  CustomProvider│
└───────┬──────────────────────────┬─────────────────────────────┘
        │                          │
        ▼                          ▼
   AbstractProvider           AbstractProvider
   • check_ready()            • check_ready()
   • mark_rate_limited()      • mark_rate_limited()
   • solve(prompt, system)    • solve(prompt, system)
```

---

## 2. AbstractProvider Interface Contract

All providers inherit from `AbstractProvider` (`providers/base.py`).

### Required Attributes & Methods

| Symbol | Type | Description |
|---|---|---|
| `name` | `str` | Unique provider identifier (e.g. `"gemini"`, `"nvidia"`, `"groq"`). |
| `cooldown` | `float` | Duration in seconds to wait after encountering an HTTP 429 rate limit (default: 300s). |
| `available` | `bool` | Current readiness state. Automatically toggled by `mark_rate_limited()` and `check_ready()`. |
| `mark_rate_limited()` | `() -> None` | Sets `available = False` and records timestamp of the 429 error. |
| `check_ready()` | `() -> bool` | Checks if `cooldown` has elapsed since `last_429` and resets `available = True` when ready. |
| `seconds_until_ready` | `property` | Returns seconds remaining in cooldown. |
| `is_429_error(exc)` | `staticmethod` | Returns `True` if exception represents a 429 / rate limit. |
| `async solve(prompt, system_prompt)` | `abstract` | Executes task solving against the LLM backend. Returns raw response text. |

---

## 3. Creating a New Provider (Example: Groq)

To add a new provider (e.g., Groq via OpenAI-compatible API):

### Step 1: Create `providers/groq.py`

```python
from __future__ import annotations

import config
from openai import AsyncOpenAI
from providers.base import AbstractProvider
from providers.retry import call_with_retry


class GroqProvider(AbstractProvider):
    def __init__(
        self,
        api_key: str = config.GROQ_API_KEY,
        model: str = config.GROQ_MODEL,
        base_url: str = config.GROQ_BASE_URL,
        name: str = "groq",
        cooldown: float = 60.0,
    ) -> None:
        super().__init__(name=name, cooldown=cooldown)
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def solve(self, prompt: str, system_prompt: str) -> str:
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

        async def _call() -> str:
            response = await client.chat.completions.create(
                model=self.model,
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

        return await call_with_retry(_call, provider_name="Groq")
```

### Step 2: Re-export in `providers/__init__.py`

```python
from providers.groq import GroqProvider
```

### Step 3: Register in `agent.py`

```python
registry = ProviderRegistry([
    GeminiProvider(runner=runner, session_service=session_service),
    NVIDIAProvider(),
    GroqProvider(),  # Priority 3 fallback
])
```

---

## 4. Provider Selection & Cooldown Flow

When `solve_task()` runs:
1. `registry.get_ready_provider()` iterates providers in registration order and returns the first ready provider (`check_ready() == True`).
2. If all providers are in cooldown, `registry.wait_for_any_provider()` calculates the shortest remaining wait time, sleeps asynchronously, and returns the recovering provider.
3. If a provider throws an HTTP 429 rate limit error during `solve()`, `provider.mark_rate_limited()` is invoked, and `solve_task()` immediately fails over to the next ready provider.
4. Non-429 errors attempt remaining ready providers before throwing a `RuntimeError`.
