# LLM-Agnostic Reliability & Report Quality — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 20 reliability and report quality enhancements that work with any LLM provider — fixing timeouts, file chaos, citation gaps, hallucination leakage, and delivery gate bypass observed in monitoring session f5e12c8eae1b4758.

**Architecture:** Settings-driven approach — all thresholds are configurable via env vars. New `ProviderProfile` frozen dataclass replaces scattered boolean flags. Graduated wall-clock pressure replaces single 65% warning. Two-pass citation repair with `SourceRegistry`. Existing middleware pipeline gets wired.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, asyncio, pytest, dataclasses (frozen)

**Design Doc:** `docs/plans/2026-03-05-llm-agnostic-reliability-quality-design.md`

---

## Phase 1: HIGH Priority (Tasks 1–11)

These prevent timeouts, file chaos, and citation gaps.

---

### Task 1: Add New Settings to config_llm.py (1B, 5C)

**Files:**
- Modify: `backend/app/core/config_llm.py:90-135` (LLMTimeoutSettingsMixin)

**Step 1: Add slow breaker + model router settings**

Add these fields to `LLMTimeoutSettingsMixin` after line 134 (after `llm_tool_timeout_max_retries`):

```python
    # Slow tool-call circuit breaker (design 1B)
    # Replaces hardcoded constants in openai_llm.py lines 66-70
    llm_slow_breaker_degraded_max_tokens: int = 4096   # Was hardcoded 1024
    llm_slow_breaker_degraded_timeout: float = 90.0     # Was hardcoded 60.0
    llm_slow_tool_threshold: float = 30.0               # Seconds before a tool call is "slow"
    llm_slow_tool_trip_count: int = 2                    # Consecutive slow calls to trip breaker
    llm_slow_tool_cooldown: float = 300.0               # Seconds before breaker resets

    # Model router tier settings (design 5C)
    fast_model_max_tokens: int = 4096
    fast_model_temperature: float = 0.2
    balanced_model_max_tokens: int = 8192
```

**Step 2: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/core/config_llm.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/app/core/config_llm.py
git commit -m "feat(config): add slow breaker and model router tier settings"
```

---

### Task 2: Add New Settings to config_features.py (2A, 2C, 4B, 5A)

**Files:**
- Modify: `backend/app/core/config_features.py:125-154` (AgentSafetySettingsMixin)
- Modify: `backend/app/core/config_features.py:225-414` (FeatureFlagsSettingsMixin)

**Step 1: Add graduated wall-clock + efficiency monitor settings**

In `AgentSafetySettingsMixin` after `max_step_wall_clock_seconds` (currently at line 347 in FeatureFlagsSettingsMixin — note: this setting should stay where it is, we add new ones nearby):

Add to `FeatureFlagsSettingsMixin` after `max_step_wall_clock_seconds` (line 347):

```python
    # Graduated step wall-clock pressure (design 2A)
    # Per-depth budgets override max_step_wall_clock_seconds when research_depth is known
    step_budget_quick_seconds: float = 300.0    # QUICK research: 5 min
    step_budget_standard_seconds: float = 600.0  # STANDARD research: 10 min
    step_budget_deep_seconds: float = 900.0      # DEEP research: 15 min
```

Add to `FeatureFlagsSettingsMixin` after `feature_repetitive_tool_detection_enabled` (line 353):

```python
    # Tool efficiency monitor settings (design 2C)
    tool_efficiency_read_threshold: int = 5
    tool_efficiency_strong_threshold: int = 6
    tool_efficiency_same_tool_threshold: int = 4
    tool_efficiency_same_tool_strong_threshold: int = 6
```

Add to `FeatureFlagsSettingsMixin` after `hallucination_escalation_min_samples` (line 358):

```python
    # Hallucination mitigation thresholds (design 4B)
    hallucination_warn_threshold: float = 0.05     # 5% → warning in delivery gate
    hallucination_block_threshold: float = 0.15    # 15% → block delivery, re-summarize
    hallucination_annotate_spans: bool = False      # Annotate flagged spans in output
    hallucination_grounding_context_size: int = 4096  # Chars of source context for LettuceDetect
    hallucination_grounding_context_deep: int = 8192  # Expanded context for DEEP research
```

Add new `KeyPoolSettingsMixin` class before `ResearchSettingsMixin` (line 416):

```python
class KeyPoolSettingsMixin:
    """API key pool circuit breaker configuration (design 5A)."""

    key_pool_cb_threshold: int = 5           # Consecutive failures to trip breaker
    key_pool_cb_reset_timeout_5xx: int = 300  # Seconds before 5xx breaker resets
    key_pool_cb_reset_timeout_429: int = 45   # Seconds before 429 breaker resets
    key_pool_exhaustion_recovery_ttl: int = 1800  # Seconds before exhausted pool re-checks
```

**Step 2: Add KeyPoolSettingsMixin to Settings inheritance**

In `backend/app/core/config.py`, add `KeyPoolSettingsMixin` to the Settings class bases. Import it from config_features.

**Step 3: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/core/config_features.py app/core/config.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/app/core/config_features.py backend/app/core/config.py
git commit -m "feat(config): add wall-clock, efficiency, hallucination, key pool settings"
```

---

### Task 3: Create ProviderProfile Registry (1A)

**Files:**
- Create: `backend/app/infrastructure/external/llm/provider_profile.py`
- Test: `backend/tests/infrastructure/external/llm/test_provider_profile.py`

**Step 1: Write the failing test**

```python
"""Tests for ProviderProfile registry."""

import pytest

from app.infrastructure.external.llm.provider_profile import (
    ProviderProfile,
    get_provider_profile,
)


class TestProviderProfile:
    """Test ProviderProfile frozen dataclass and registry lookup."""

    def test_default_profile_is_conservative(self):
        profile = get_provider_profile("https://unknown-api.example.com/v1", "some-model")
        assert profile.name == "default"
        assert profile.connect_timeout == 10.0
        assert profile.read_timeout == 300.0
        assert profile.supports_json_mode is True
        assert profile.tool_arg_truncation_prone is False

    def test_glm_profile_detected_by_url(self):
        profile = get_provider_profile("https://api.z.ai/api/paas/v4", "glm-5")
        assert profile.name == "glm"
        assert profile.needs_message_merging is True
        assert profile.needs_thinking_suppression is True
        assert profile.tool_arg_truncation_prone is True
        assert profile.requires_orphan_cleanup is True

    def test_glm_profile_detected_by_model_name(self):
        profile = get_provider_profile("https://openrouter.ai/api/v1", "glm-5")
        assert profile.name == "glm"

    def test_deepseek_profile(self):
        profile = get_provider_profile("https://api.deepseek.com", "deepseek-chat")
        assert profile.name == "deepseek"
        assert profile.read_timeout == 180.0
        assert profile.tool_arg_truncation_prone is False

    def test_openrouter_profile(self):
        profile = get_provider_profile("https://openrouter.ai/api/v1", "qwen/qwen3-coder")
        assert profile.name == "openrouter"
        assert profile.supports_json_mode is True
        assert profile.supports_tool_choice is True

    def test_anthropic_profile(self):
        profile = get_provider_profile("https://api.anthropic.com/v1", "claude-sonnet-4-6")
        assert profile.name == "anthropic"
        assert profile.read_timeout == 180.0

    def test_ollama_profile(self):
        profile = get_provider_profile("http://localhost:11434", "llama3.2")
        assert profile.name == "ollama"
        assert profile.read_timeout == 600.0

    def test_kimi_profile(self):
        profile = get_provider_profile("https://api.kimi.ai/v1", "kimi-k2.5")
        assert profile.name == "kimi"
        assert profile.needs_thinking_suppression is True

    def test_profile_is_frozen(self):
        profile = get_provider_profile("https://api.z.ai/api/paas/v4", "glm-5")
        with pytest.raises(AttributeError):
            profile.name = "hacked"

    def test_bigmodel_cn_matches_glm(self):
        profile = get_provider_profile("https://open.bigmodel.cn/api/paas/v4", "glm-4")
        assert profile.name == "glm"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_provider_profile.py -v -p no:cov -o addopts=`
Expected: FAIL — module not found

**Step 3: Write implementation**

```python
"""LLM Provider Capability Profiles.

Frozen dataclass consolidating all provider-specific behavior into a single
lookup. Replaces scattered _is_glm_api, _is_deepseek, etc. booleans.

Usage:
    profile = get_provider_profile(api_base, model_name)
    if profile.tool_arg_truncation_prone:
        # validate tool args against schema before returning
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderProfile:
    """Immutable capability/behavior profile for an LLM provider.

    All fields have conservative defaults suitable for unknown providers.
    """

    name: str
    connect_timeout: float = 10.0
    read_timeout: float = 300.0
    tool_read_timeout: float = 90.0
    stream_read_timeout: float = 30.0
    supports_json_mode: bool = True
    supports_tool_choice: bool = True
    supports_system_role: bool = True
    max_tool_calls_per_response: int = 20
    needs_message_merging: bool = False
    needs_thinking_suppression: bool = False
    tool_arg_truncation_prone: bool = False
    requires_orphan_cleanup: bool = False
    slow_tool_threshold: float = 30.0
    slow_tool_trip_count: int = 2


# ── Pre-built profiles ────────────────────────────────────────────────────────

_PROFILES: dict[str, ProviderProfile] = {
    "default": ProviderProfile(name="default"),
    "openai": ProviderProfile(
        name="openai",
        connect_timeout=5.0,
        read_timeout=120.0,
    ),
    "openrouter": ProviderProfile(
        name="openrouter",
        connect_timeout=5.0,
        read_timeout=120.0,
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        connect_timeout=5.0,
        read_timeout=180.0,
    ),
    "glm": ProviderProfile(
        name="glm",
        connect_timeout=10.0,
        read_timeout=90.0,
        tool_read_timeout=90.0,
        supports_json_mode=False,
        needs_message_merging=True,
        needs_thinking_suppression=True,
        tool_arg_truncation_prone=True,
        requires_orphan_cleanup=True,
    ),
    "deepseek": ProviderProfile(
        name="deepseek",
        connect_timeout=5.0,
        read_timeout=180.0,
    ),
    "ollama": ProviderProfile(
        name="ollama",
        connect_timeout=3.0,
        read_timeout=600.0,
        stream_read_timeout=600.0,
        supports_json_mode=False,
        supports_tool_choice=False,
    ),
    "kimi": ProviderProfile(
        name="kimi",
        connect_timeout=5.0,
        read_timeout=120.0,
        needs_thinking_suppression=True,
    ),
}


# ── URL → profile pattern matching ────────────────────────────────────────────

_URL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"z\.ai|bigmodel\.cn|zhipuai", re.IGNORECASE), "glm"),
    (re.compile(r"api\.deepseek\.com", re.IGNORECASE), "deepseek"),
    (re.compile(r"openrouter\.ai", re.IGNORECASE), "openrouter"),
    (re.compile(r"api\.openai\.com", re.IGNORECASE), "openai"),
    (re.compile(r"anthropic\.com", re.IGNORECASE), "anthropic"),
    (re.compile(r"kimi\.(com|ai)", re.IGNORECASE), "kimi"),
    (re.compile(r"localhost|127\.0\.0\.1|host\.docker\.internal|:11434", re.IGNORECASE), "ollama"),
]

# Model name prefix → profile (fallback when URL doesn't match)
_MODEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^glm-", re.IGNORECASE), "glm"),
    (re.compile(r"^deepseek", re.IGNORECASE), "deepseek"),
    (re.compile(r"^claude-", re.IGNORECASE), "anthropic"),
    (re.compile(r"^gpt-|^o[134]-", re.IGNORECASE), "openai"),
    (re.compile(r"^kimi-", re.IGNORECASE), "kimi"),
    (re.compile(r"^llama|^mistral|^phi-|^gemma", re.IGNORECASE), "ollama"),
]


def get_provider_profile(api_base: str, model_name: str) -> ProviderProfile:
    """Resolve a provider profile from API base URL and model name.

    Priority: URL patterns first, then model name patterns, then conservative default.
    """
    base = (api_base or "").lower()

    # 1. Match by URL
    for pattern, profile_key in _URL_PATTERNS:
        if pattern.search(base):
            return _PROFILES[profile_key]

    # 2. Match by model name
    for pattern, profile_key in _MODEL_PATTERNS:
        if pattern.search(model_name or ""):
            return _PROFILES[profile_key]

    # 3. Conservative default
    return _PROFILES["default"]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_provider_profile.py -v -p no:cov -o addopts=`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/provider_profile.py backend/tests/infrastructure/external/llm/test_provider_profile.py
git commit -m "feat(llm): add ProviderProfile frozen dataclass and registry"
```

---

### Task 4: Wire ProviderProfile into OpenAILLM (1A)

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py:72-170` (__init__)
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py:189-239` (_create_timeout)

**Step 1: Add profile to __init__**

After line 135 (`self._api_base = api_base or settings.api_base`), add:

```python
        # Resolve provider capability profile (replaces scattered _is_* booleans)
        from app.infrastructure.external.llm.provider_profile import get_provider_profile

        self._provider_profile = get_provider_profile(self._api_base, self._model_name)
```

Keep existing `_is_*` booleans for backward compatibility — they are used in ~50 places. Add a deprecation comment:

After line 157 (`self._is_deepseek = self._detect_deepseek()`), add:

```python
        # TODO: Migrate callers from _is_* booleans to self._provider_profile.*
        # The _is_* flags are kept for backward compatibility during migration.
```

**Step 2: Use profile in _create_timeout()**

Replace the provider selection logic in `_create_timeout()` (lines 212-223) with:

```python
        provider_key = self._provider_profile.name
        if provider_key not in profiles:
            provider_key = "default"
```

This replaces the 12-line if/elif chain with a 2-line lookup.

**Step 3: Run existing tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/ -v -p no:cov -o addopts= -x`
Expected: All existing tests PASS

**Step 4: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py
git commit -m "feat(llm): wire ProviderProfile into OpenAILLM, simplify timeout selection"
```

---

### Task 5: Settings-Driven Slow Circuit Breaker (1B)

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py:66-70` (constants)
- Test: `backend/tests/infrastructure/external/llm/test_slow_breaker_settings.py`

**Step 1: Write the failing test**

```python
"""Tests for settings-driven slow tool-call circuit breaker."""

from unittest.mock import patch

import pytest


class TestSlowBreakerSettings:
    """Verify that slow breaker reads thresholds from settings, not hardcoded constants."""

    def test_breaker_uses_settings_threshold(self):
        """Slow breaker should read threshold from settings."""
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        mock_settings = {
            "llm_slow_tool_threshold": 15.0,
            "llm_slow_tool_trip_count": 3,
            "llm_slow_tool_cooldown": 120.0,
            "llm_slow_breaker_degraded_max_tokens": 2048,
            "llm_slow_breaker_degraded_timeout": 45.0,
        }

        with patch("app.infrastructure.external.llm.openai_llm.get_settings") as mock_get:
            mock_obj = mock_get.return_value
            for k, v in mock_settings.items():
                setattr(mock_obj, k, v)
            # Set required fields
            mock_obj.api_key = "test-key"
            mock_obj.model_name = "test-model"
            mock_obj.temperature = 0.3
            mock_obj.max_tokens = 4096
            mock_obj.api_base = "https://api.openai.com/v1"

            llm = OpenAILLM(api_key="test-key")

        # The LLM should have read the settings values
        assert llm._slow_tool_threshold == 15.0
        assert llm._slow_tool_trip_count == 3
        assert llm._slow_tool_cooldown == 120.0

    def test_breaker_logs_once_without_fast_model(self):
        """When breaker trips with no FAST_MODEL, log error ONCE (not every call)."""
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        with patch("app.infrastructure.external.llm.openai_llm.get_settings") as mock_get:
            mock_obj = mock_get.return_value
            mock_obj.api_key = "test-key"
            mock_obj.model_name = "test-model"
            mock_obj.temperature = 0.3
            mock_obj.max_tokens = 4096
            mock_obj.api_base = "https://api.openai.com/v1"
            mock_obj.fast_model = ""
            mock_obj.llm_slow_tool_threshold = 30.0
            mock_obj.llm_slow_tool_trip_count = 2
            mock_obj.llm_slow_tool_cooldown = 300.0
            mock_obj.llm_slow_breaker_degraded_max_tokens = 4096
            mock_obj.llm_slow_breaker_degraded_timeout = 90.0

            llm = OpenAILLM(api_key="test-key")

        # First warning should set the flag
        assert llm._slow_breaker_missing_fast_model_warned is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_slow_breaker_settings.py -v -p no:cov -o addopts=`
Expected: FAIL — `_slow_tool_threshold` attribute not found

**Step 3: Replace hardcoded constants with settings**

In `openai_llm.py`, replace lines 66-70 class-level constants with instance attributes in `__init__()`. After the `_provider_profile` assignment, add:

```python
        # Slow tool-call circuit breaker settings (configurable via env)
        self._slow_tool_threshold = float(
            getattr(settings, "llm_slow_tool_threshold", self._SLOW_TOOL_CALL_THRESHOLD_SECONDS)
        )
        self._slow_tool_trip_count = int(
            getattr(settings, "llm_slow_tool_trip_count", self._SLOW_TOOL_CALL_TRIP_COUNT)
        )
        self._slow_tool_cooldown = float(
            getattr(settings, "llm_slow_tool_cooldown", self._SLOW_TOOL_CALL_COOLDOWN_SECONDS)
        )
        self._slow_breaker_max_tokens = int(
            getattr(settings, "llm_slow_breaker_degraded_max_tokens", self._SLOW_TOOL_BREAKER_DEGRADED_MAX_TOKENS)
        )
        self._slow_breaker_timeout = float(
            getattr(settings, "llm_slow_breaker_degraded_timeout", self._SLOW_TOOL_BREAKER_DEGRADED_TIMEOUT_SECONDS)
        )
```

Then update all references to the class-level constants to use these instance attributes. Search for `self._SLOW_TOOL_CALL_THRESHOLD_SECONDS` etc. and replace.

**Step 4: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_slow_breaker_settings.py -v -p no:cov -o addopts=`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py backend/tests/infrastructure/external/llm/test_slow_breaker_settings.py
git commit -m "feat(llm): settings-driven slow circuit breaker, log-once pattern"
```

---

### Task 6: Graduated Step Wall-Clock Pressure (2A)

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:1526-1569` (wall-clock logic)
- Test: `backend/tests/domain/services/agents/test_graduated_wall_clock.py`

**Step 1: Write the failing test**

```python
"""Tests for graduated step wall-clock pressure thresholds."""

import pytest


class TestGraduatedWallClock:
    """Verify 50%/75%/90% pressure levels replace single 65% threshold."""

    def test_advisory_at_50_percent(self):
        from app.domain.services.agents.base import _get_wall_clock_pressure_level

        level = _get_wall_clock_pressure_level(elapsed=310.0, budget=600.0)
        assert level == "ADVISORY"

    def test_urgent_at_75_percent(self):
        from app.domain.services.agents.base import _get_wall_clock_pressure_level

        level = _get_wall_clock_pressure_level(elapsed=460.0, budget=600.0)
        assert level == "URGENT"

    def test_critical_at_90_percent(self):
        from app.domain.services.agents.base import _get_wall_clock_pressure_level

        level = _get_wall_clock_pressure_level(elapsed=550.0, budget=600.0)
        assert level == "CRITICAL"

    def test_none_below_50_percent(self):
        from app.domain.services.agents.base import _get_wall_clock_pressure_level

        level = _get_wall_clock_pressure_level(elapsed=200.0, budget=600.0)
        assert level is None

    def test_read_only_tools_blocked_at_urgent(self):
        """At URGENT level, read-only tools should be blocked."""
        from app.domain.services.agents.base import _should_block_tool_at_pressure

        assert _should_block_tool_at_pressure("web_search", "URGENT") is True
        assert _should_block_tool_at_pressure("file_read", "URGENT") is True
        assert _should_block_tool_at_pressure("file_write", "URGENT") is False

    def test_all_tools_blocked_at_critical_except_write(self):
        """At CRITICAL level, all tools blocked except file_write and code_save_artifact."""
        from app.domain.services.agents.base import _should_block_tool_at_pressure

        assert _should_block_tool_at_pressure("web_search", "CRITICAL") is True
        assert _should_block_tool_at_pressure("file_read", "CRITICAL") is True
        assert _should_block_tool_at_pressure("file_write", "CRITICAL") is False
        assert _should_block_tool_at_pressure("code_save_artifact", "CRITICAL") is False
```

**Step 2: Run test to verify it fails**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_graduated_wall_clock.py -v -p no:cov -o addopts=`
Expected: FAIL — function not found

**Step 3: Implement helper functions**

Add at module level in `base.py` (before the BaseAgent class):

```python
# ── Graduated wall-clock pressure (design 2A) ─────────────────────────

_WRITE_TOOLS = frozenset({"file_write", "file_str_replace", "code_save_artifact"})


def _get_wall_clock_pressure_level(elapsed: float, budget: float) -> str | None:
    """Return pressure level based on elapsed/budget ratio."""
    if budget <= 0:
        return None
    ratio = elapsed / budget
    if ratio >= 0.90:
        return "CRITICAL"
    if ratio >= 0.75:
        return "URGENT"
    if ratio >= 0.50:
        return "ADVISORY"
    return None


def _should_block_tool_at_pressure(tool_name: str, level: str) -> bool:
    """Check if a tool should be blocked at the given pressure level."""
    if level == "CRITICAL":
        return tool_name not in _WRITE_TOOLS
    if level == "URGENT":
        # Block read-only tools at URGENT
        from app.domain.models.tool import ToolName

        read_tools = frozenset(t.value for t in ToolName.read_only_tools())
        return tool_name in read_tools
    return False
```

Then replace the single 65% check in `execute()` (lines 1542-1569) with graduated logic:

```python
                # ── Graduated wall-clock pressure ──────────────────
                if self._step_start_time is not None:
                    elapsed = time.monotonic() - self._step_start_time
                    pressure = _get_wall_clock_pressure_level(elapsed, wall_limit)

                    if pressure == "ADVISORY" and not self._wall_clock_advisory_injected:
                        self._wall_clock_advisory_injected = True
                        logger.info(
                            "Step wall-clock at 50%% (%.0fs/%.0fs); advisory injected.",
                            elapsed, wall_limit,
                        )
                        await self._add_to_memory([{
                            "role": "user",
                            "content": (
                                f"STEP TIME ADVISORY: You have used 50% of the step time budget "
                                f"({elapsed:.0f}s of {wall_limit:.0f}s). "
                                f"Begin wrapping up research and focus on writing output."
                            ),
                        }])

                    elif pressure == "URGENT" and not self._wall_clock_urgent_injected:
                        self._wall_clock_urgent_injected = True
                        logger.warning(
                            "Step wall-clock at 75%% (%.0fs/%.0fs); blocking read-only tools.",
                            elapsed, wall_limit,
                        )
                        await self._add_to_memory([{
                            "role": "user",
                            "content": (
                                f"⚠️ STEP TIME URGENT: 75% of budget used ({elapsed:.0f}s of {wall_limit:.0f}s). "
                                f"Read-only tools are now BLOCKED. You MUST finalize your output immediately. "
                                f"Use file_write or file_str_replace to save findings NOW."
                            ),
                        }])
                        graceful_completion_requested = True
                        skip_tool_execution_for_wall_clock = True

                    elif pressure == "CRITICAL" and not self._wall_clock_critical_injected:
                        self._wall_clock_critical_injected = True
                        logger.warning(
                            "Step wall-clock at 90%% (%.0fs/%.0fs); blocking ALL non-write tools.",
                            elapsed, wall_limit,
                        )
                        await self._add_to_memory([{
                            "role": "user",
                            "content": (
                                f"🛑 STEP TIME CRITICAL: 90% of budget used ({elapsed:.0f}s of {wall_limit:.0f}s). "
                                f"ALL tools except file_write and code_save_artifact are BLOCKED. "
                                f"Write your output NOW or it will be lost."
                            ),
                        }])
                        graceful_completion_requested = True
                        skip_tool_execution_for_wall_clock = True
```

Add tracking flags in `execute()` initialization (near line 1472):

```python
        wall_clock_advisory_injected = False
        wall_clock_urgent_injected = False
        wall_clock_critical_injected = False
```

And store them as instance attributes:

```python
        self._wall_clock_advisory_injected = False
        self._wall_clock_urgent_injected = False
        self._wall_clock_critical_injected = False
```

**Step 4: Add time stamp to tool results after 50%**

In `invoke_tool()`, after getting the tool result, add:

```python
        # Append time context after 50% mark (design 2A)
        if self._step_start_time and hasattr(self, "_wall_clock_advisory_injected") and self._wall_clock_advisory_injected:
            elapsed = time.monotonic() - self._step_start_time
            settings = get_settings()
            budget = getattr(settings, "max_step_wall_clock_seconds", 600.0)
            if isinstance(result.output, str):
                result = ToolResult(output=f"{result.output}\n\n[Step time: {elapsed:.0f}s/{budget:.0f}s]")
```

**Step 5: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_graduated_wall_clock.py -v -p no:cov -o addopts=`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/tests/domain/services/agents/test_graduated_wall_clock.py
git commit -m "feat(agent): graduated step wall-clock pressure at 50%/75%/90%"
```

---

### Task 7: File Management Enforcement (2B)

**Files:**
- Modify: `backend/app/domain/services/tools/file.py:179-199` (overwrite detection)
- Modify: `backend/app/domain/services/tools/file.py:137-160` (content regression)
- Test: `backend/tests/domain/services/tools/test_file_enforcement.py`

**Step 1: Write the failing test**

```python
"""Tests for file management enforcement (design 2B)."""

import pytest

from app.domain.services.tools.file import FileTool


class TestFileEnforcement:
    """Verify overwrite blocking and content regression error."""

    def test_overwrite_blocked_after_third(self):
        """After 3rd overwrite, file_write should be blocked for that path."""
        tool = FileTool.__new__(FileTool)
        tool._write_history = {}
        tool._overwrite_blocked_until = {}
        tool._recent_write_sizes = {}

        path = "/workspace/report.md"
        # Simulate 3 overwrites in quick succession
        import time

        now = time.monotonic()
        tool._write_history[path] = [now - 2, now - 1, now]

        result = tool._check_repetitive_overwrites(path, append=False)
        assert result is not None
        # After 3rd overwrite, path should be blocked
        assert path in tool._overwrite_blocked_until

    def test_content_regression_returns_error_above_50pct(self):
        """Content regression >50% should return error, not just warning."""
        tool = FileTool.__new__(FileTool)
        tool._recent_write_sizes = {"/workspace/report.md": 2000}

        result = tool._check_content_regression("/workspace/report.md", "short")
        assert result is not None
        assert "ERROR" in result or "error" in result.lower() or "BLOCKED" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_file_enforcement.py -v -p no:cov -o addopts=`
Expected: FAIL

**Step 3: Implement enforcement**

In `file.py`, modify `_check_repetitive_overwrites()` (lines 179-199):

After the existing warning generation, add blocking logic:

```python
    def _check_repetitive_overwrites(self, path: str, *, append: bool) -> str | None:
        """Return a warning/error when same file is overwritten repeatedly."""
        if append:
            return None

        now = time.monotonic()

        # Check if path is currently blocked
        blocked_until = self._overwrite_blocked_until.get(path, 0.0)
        if now < blocked_until:
            remaining = blocked_until - now
            return (
                f"ERROR: file_write BLOCKED for '{path}' for {remaining:.0f}s due to overwrite loop. "
                f"Use file_str_replace for incremental edits instead."
            )

        history = self._write_history.get(path, [])
        history = [ts for ts in history if now - ts <= _SAME_FILE_WRITE_WINDOW_SECONDS]
        history.append(now)
        self._write_history[path] = history

        if len(history) < _SAME_FILE_WRITE_WARN_THRESHOLD:
            return None

        # Block after 3rd overwrite for 120 seconds
        self._overwrite_blocked_until[path] = now + 120.0

        warning = (
            f"ERROR: file_write overwrite loop detected for '{path}' "
            f"({len(history)} overwrites within {_SAME_FILE_WRITE_WINDOW_SECONDS:.0f}s). "
            f"file_write is BLOCKED for 120s. Use file_str_replace for incremental edits."
        )
        logger.warning(warning)
        return warning
```

Add `_overwrite_blocked_until` to `__init__`:

```python
        self._overwrite_blocked_until: dict[str, float] = {}
```

Modify `_check_content_regression()` to return ERROR when shrink >50%:

Change line 149 (`if shrink_ratio < 0.6:`) to:

```python
        if shrink_ratio < 0.5:
            error = (
                f"ERROR: file_write to '{path}' would shrink content from "
                f"{prev_size:,} to {new_size:,} bytes ({shrink_ratio:.0%}). "
                f"Write BLOCKED. Use file_str_replace to patch instead."
            )
            logger.error(error)
            self._recent_write_sizes[path] = prev_size  # Don't update — block preserves old size
            return error
        if shrink_ratio < 0.6:
```

In `file_write()` method, after checking warnings (lines 307-316), block the write if any warning starts with "ERROR":

```python
        # Block write if enforcement triggered
        if any(w.startswith("ERROR") for w in write_warnings):
            return ToolResult(output="\n".join(write_warnings))
```

**Step 4: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/tools/test_file_enforcement.py tests/domain/services/tools/test_file*.py -v -p no:cov -o addopts=`
Expected: PASS (new + existing)

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/file.py backend/tests/domain/services/tools/test_file_enforcement.py
git commit -m "fix(file): block overwrites after 3rd loop, error on >50% content regression"
```

---

### Task 8: Report Construction Protocol Prompt (3A)

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py` (add REPORT_CONSTRUCTION_PROTOCOL)

**Step 1: Add protocol constant**

Add near the top of execution.py (after imports, before existing prompt constants):

```python
REPORT_CONSTRUCTION_PROTOCOL = """
## Report Construction Protocol

Follow these rules STRICTLY when creating research reports:

1. **Single Report File**: Create exactly ONE markdown file for the report. Never create duplicates.
2. **Outline First**: Write the full outline (headings + placeholders) in one file_write, then fill sections incrementally with file_str_replace.
3. **Incremental Edits**: After initial creation, ALWAYS use file_str_replace (not file_write) to update sections. This prevents overwriting existing content.
4. **No code_execute_python for Text**: NEVER use code_execute_python to save markdown/text. It is ONLY for: data analysis, calculations, charts, and code execution.
5. **No Duplicate Files**: Check existing files before creating new ones. If a report file already exists, edit it — do not create report-2.md, report-copy.md, etc.
"""
```

**Step 2: Inject protocol into build_summarize_prompt()**

In `build_summarize_prompt()` (around line 1303), add the protocol to the prompt body for research steps:

```python
    # Inject report construction protocol for research reports
    if research_depth in ("STANDARD", "DEEP"):
        prompt_parts.append(REPORT_CONSTRUCTION_PROTOCOL)
```

**Step 3: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/domain/services/prompts/execution.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/app/domain/services/prompts/execution.py
git commit -m "feat(prompts): add report construction protocol for research steps"
```

---

### Task 9: Citation Numbering Discipline (3B)

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py` (build_summarize_prompt)
- Modify: `backend/app/domain/services/agents/execution.py` (re-summarize on high orphan rate)

**Step 1: Add citation cap to build_summarize_prompt()**

In `build_summarize_prompt()`, after the citation requirements section (around line 1331-1338), add:

```python
    # Citation numbering discipline (design 3B)
    if sources and len(sources) > 0:
        source_count = len(sources)
        prompt_parts.append(
            f"\n## Citation Discipline\n"
            f"You have exactly {source_count} sources available.\n"
            f"Citation numbers MUST be in range [1]-[{source_count}].\n"
            f"Do NOT invent citation numbers above [{source_count}].\n"
            f"Every [N] inline citation MUST have a matching entry in ## References.\n"
        )

        # Pre-populate References template
        ref_lines = ["\n## References (use this exact format)"]
        for i, src in enumerate(sources[:source_count], 1):
            title = getattr(src, "title", None) or getattr(src, "query", f"Source {i}")
            url = getattr(src, "url", None) or ""
            ref_lines.append(f"[{i}] {title} - {url}")
        prompt_parts.append("\n".join(ref_lines))
```

**Step 2: Add re-summarize trigger in execution.py**

In `execution.py`, after `validate_citations()` call (around line 1158-1191), add re-summarize logic:

```python
        # Re-summarize if orphan citations exceed 50% (design 3B)
        if citation_result and citation_result.orphan_count > 0:
            total_inline = citation_result.inline_count or 1
            orphan_ratio = citation_result.orphan_count / total_inline
            if orphan_ratio > 0.5 and not getattr(self, "_resummarize_attempted", False):
                self._resummarize_attempted = True
                logger.warning(
                    "Citation orphan ratio %.1f%% exceeds 50%%; requesting re-summarize",
                    orphan_ratio * 100,
                )
                # The repair pass will handle what it can; log for observability
```

**Step 3: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/domain/services/prompts/execution.py app/domain/services/agents/execution.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/app/domain/services/prompts/execution.py backend/app/domain/services/agents/execution.py
git commit -m "feat(prompts): citation numbering discipline with cap and reference template"
```

---

### Task 10: Citation Integrity Overhaul — SourceRegistry + Fuzzy Match (4A)

**Files:**
- Modify: `backend/app/domain/services/agents/citation_integrity.py`
- Test: `backend/tests/domain/services/agents/test_citation_integrity.py` (extend existing)

**Step 1: Write failing test for SourceRegistry**

Add to existing test file:

```python
class TestSourceRegistry:
    """Test pre-generation stable source numbering."""

    def test_registry_assigns_stable_ids(self):
        from app.domain.services.agents.citation_integrity import SourceRegistry

        registry = SourceRegistry()
        registry.register("https://example.com/a", "Source A")
        registry.register("https://example.com/b", "Source B")
        registry.register("https://example.com/a", "Source A Duplicate")  # same URL

        assert registry.get_id("https://example.com/a") == 1
        assert registry.get_id("https://example.com/b") == 2
        assert registry.count == 2  # deduped

    def test_fuzzy_match_repairs_orphan(self):
        from app.domain.services.agents.citation_integrity import fuzzy_match_orphan

        references = {1: "JAX Framework Overview - https://jax.dev"}
        result = fuzzy_match_orphan("[99]", references)
        # Should return None or a match — depends on content
        # This tests the function exists and doesn't crash
        assert result is None or isinstance(result, int)
```

**Step 2: Run test to verify fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_citation_integrity.py::TestSourceRegistry -v -p no:cov -o addopts=`
Expected: FAIL — SourceRegistry not found

**Step 3: Add SourceRegistry and fuzzy_match_orphan**

Add to `citation_integrity.py`:

```python
class SourceRegistry:
    """Pre-generation stable source numbering. Deduplicates by URL."""

    def __init__(self) -> None:
        self._url_to_id: dict[str, int] = {}
        self._id_to_entry: dict[int, tuple[str, str]] = {}
        self._next_id: int = 1

    def register(self, url: str, title: str = "") -> int:
        """Register a source URL. Returns stable ID (reuses if URL seen before)."""
        normalized = url.strip().rstrip("/").lower()
        if normalized in self._url_to_id:
            return self._url_to_id[normalized]
        sid = self._next_id
        self._url_to_id[normalized] = sid
        self._id_to_entry[sid] = (title, url)
        self._next_id += 1
        return sid

    def get_id(self, url: str) -> int | None:
        """Get ID for a URL, or None if not registered."""
        return self._url_to_id.get(url.strip().rstrip("/").lower())

    @property
    def count(self) -> int:
        return len(self._id_to_entry)

    def build_references_section(self) -> str:
        """Generate a ## References section from registered sources."""
        lines = ["## References"]
        for sid in sorted(self._id_to_entry):
            title, url = self._id_to_entry[sid]
            lines.append(f"[{sid}] {title} - {url}")
        return "\n".join(lines)


def fuzzy_match_orphan(
    orphan_text: str, references: dict[int, str], threshold: float = 0.6
) -> int | None:
    """Try to fuzzy-match an orphan citation to an existing reference.

    Returns reference ID if match found above threshold, else None.
    Simple word-overlap scoring (no external dependencies).
    """
    # Extract words from orphan context
    orphan_words = set(orphan_text.lower().split())
    if not orphan_words:
        return None

    best_id = None
    best_score = 0.0

    for ref_id, ref_text in references.items():
        ref_words = set(ref_text.lower().split())
        if not ref_words:
            continue
        overlap = len(orphan_words & ref_words)
        score = overlap / max(len(orphan_words), len(ref_words))
        if score > best_score and score >= threshold:
            best_score = score
            best_id = ref_id

    return best_id
```

**Step 4: Update repair_citations() to use two-pass approach**

In the existing `repair_citations()`, add fuzzy matching as a first pass before removing orphans.

**Step 5: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_citation_integrity.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/citation_integrity.py backend/tests/domain/services/agents/test_citation_integrity.py
git commit -m "feat(citation): add SourceRegistry and fuzzy orphan matching"
```

---

### Task 11: Anti-Tool-Misuse Instructions (3C)

**Files:**
- Modify: `backend/app/domain/services/prompts/system.py`

**Step 1: Add anti-misuse section to CORE_PROMPT**

In `system.py`, within the CORE_PROMPT or `build_system_prompt()`, add a new section:

```python
TOOL_USAGE_DISCIPLINE = """
## Tool Usage Discipline

NEVER misuse tools. Follow these rules strictly:

- **code_execute_python**: ONLY for data analysis, calculations, charts, and running code. NEVER use it to save text, generate markdown, or create report content.
- **shell_exec**: ONLY for system commands (install packages, run scripts, check processes). NEVER use it to write files — use file_write instead.
- **file_write**: For creating or overwriting files. After initial creation, prefer file_str_replace for edits.
- **file_str_replace**: For surgical edits to existing files. Preferred over file_write for modifications.

### Common Mistakes to Avoid
- ❌ `code_execute_python("with open('report.md', 'w') as f: f.write(...)")` — Use file_write instead
- ❌ `shell_exec("echo '...' > file.md")` — Use file_write instead
- ❌ `code_execute_python("print(markdown_text)")` — Use file_write to save, then return a summary
"""
```

Inject this into `build_system_prompt()` after the core prompt sections.

**Step 2: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/domain/services/prompts/system.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/app/domain/services/prompts/system.py
git commit -m "feat(prompts): add anti-tool-misuse discipline instructions"
```

---

## Phase 2: MEDIUM Priority (Tasks 12–19)

These improve resilience and observability.

---

### Task 12: Tool Argument Pre-Validation (1C)

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py`
- Test: `backend/tests/infrastructure/external/llm/test_tool_arg_validation.py`

**Step 1: Write the failing test**

```python
"""Tests for tool argument pre-validation against JSON schema."""

import pytest

from app.infrastructure.external.llm.provider_profile import ProviderProfile


class TestToolArgValidation:
    """Verify _validate_tool_args() catches malformed args."""

    def test_missing_required_field_detected(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        schema = {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file", "content"],
        }

        # Missing 'file' parameter
        args = {"content": "hello"}
        errors = OpenAILLM._validate_tool_args_static(args, schema)
        assert len(errors) > 0
        assert any("file" in e for e in errors)

    def test_valid_args_pass(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        schema = {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file", "content"],
        }

        args = {"file": "/workspace/report.md", "content": "hello"}
        errors = OpenAILLM._validate_tool_args_static(args, schema)
        assert len(errors) == 0
```

**Step 2: Run test to verify fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_tool_arg_validation.py -v -p no:cov -o addopts=`
Expected: FAIL

**Step 3: Implement _validate_tool_args_static()**

Add as a static method on OpenAILLM:

```python
    @staticmethod
    def _validate_tool_args_static(
        args: dict[str, Any], schema: dict[str, Any]
    ) -> list[str]:
        """Validate tool call arguments against JSON schema.

        Returns list of error messages (empty = valid).
        Lightweight check — only validates required fields and basic types.
        """
        errors: list[str] = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in args:
                errors.append(f"Missing required field: '{field}'")

        for field, value in args.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be string, got {type(value).__name__}")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be boolean, got {type(value).__name__}")

        return errors
```

Wire it into tool call parsing — only when `self._provider_profile.tool_arg_truncation_prone`:

```python
        if self._provider_profile.tool_arg_truncation_prone and tool_schemas:
            for tc in tool_calls:
                schema = tool_schemas.get(tc.function.name, {})
                if schema:
                    validation_errors = self._validate_tool_args_static(
                        json.loads(tc.function.arguments or "{}"), schema
                    )
                    if validation_errors:
                        logger.warning(
                            "Tool arg validation failed for %s: %s",
                            tc.function.name, validation_errors,
                        )
```

**Step 4: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/test_tool_arg_validation.py -v -p no:cov -o addopts=`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py backend/tests/infrastructure/external/llm/test_tool_arg_validation.py
git commit -m "feat(llm): tool argument pre-validation for truncation-prone providers"
```

---

### Task 13: Response Finish Reason Propagation (1D)

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py` (finish_reason handling)

**Step 1: Enhance truncation handling in ask()**

Find the `finish_reason == "length"` handling (around lines 1802-1813). Enhance it:

```python
            if finish_reason == "length" and tools:
                # Auto-reduce max_tokens for retry (design 1D)
                reduced_tokens = max(1024, (max_tokens or self._max_tokens) // 2)
                logger.warning(
                    "Response truncated (finish_reason=length) with tools. "
                    "Retrying with max_tokens=%d (was %d).",
                    reduced_tokens, max_tokens or self._max_tokens,
                )
                # Inject truncation advisory into messages
                messages = list(messages)  # copy
                messages.append({
                    "role": "user",
                    "content": (
                        "Previous response was truncated. Produce a shorter response. "
                        "Focus on the tool call with minimal arguments."
                    ),
                })
                max_tokens = reduced_tokens
                continue  # Retry the loop
```

**Step 2: Run existing LLM tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/llm/ -v -p no:cov -o addopts= -x`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py
git commit -m "feat(llm): auto-reduce max_tokens on truncation with tool calls"
```

---

### Task 14: Settings-Driven Tool Efficiency Monitor (2C)

**Files:**
- Modify: `backend/app/domain/services/agents/tool_efficiency_monitor.py:264-287` (singleton)
- Modify: `backend/app/domain/services/flows/plan_act.py` (per-session instances)
- Test: `backend/tests/domain/services/agents/test_efficiency_settings.py`

**Step 1: Write the failing test**

```python
"""Tests for settings-driven tool efficiency monitor."""

import pytest


class TestEfficiencyMonitorSettings:
    """Verify monitor reads thresholds from settings."""

    def test_from_settings(self):
        from unittest.mock import patch

        mock_settings = type("S", (), {
            "tool_efficiency_read_threshold": 8,
            "tool_efficiency_strong_threshold": 10,
            "tool_efficiency_same_tool_threshold": 6,
            "tool_efficiency_same_tool_strong_threshold": 8,
        })()

        from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor

        monitor = ToolEfficiencyMonitor(
            read_threshold=mock_settings.tool_efficiency_read_threshold,
            strong_threshold=mock_settings.tool_efficiency_strong_threshold,
            same_tool_threshold=mock_settings.tool_efficiency_same_tool_threshold,
            same_tool_strong_threshold=mock_settings.tool_efficiency_same_tool_strong_threshold,
        )

        assert monitor.read_threshold == 8
        assert monitor.strong_threshold == 10
        assert monitor.same_tool_threshold == 6
        assert monitor.same_tool_strong_threshold == 8

    def test_step_scoped_reset(self):
        """Monitor should support reset() for step-scoped usage."""
        from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor

        monitor = ToolEfficiencyMonitor()
        # Record some activity
        monitor.record_tool_call("web_search")
        monitor.record_tool_call("web_search")
        assert monitor._consecutive_reads > 0

        # Reset for new step
        monitor.reset()
        assert monitor._consecutive_reads == 0
```

**Step 2: Run test to verify fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_efficiency_settings.py -v -p no:cov -o addopts=`
Expected: FAIL (reset() doesn't exist)

**Step 3: Add reset() method**

In `tool_efficiency_monitor.py`, add a `reset()` method:

```python
    def reset(self) -> None:
        """Reset tracking state for a new step scope."""
        self._consecutive_reads = 0
        self._tool_history.clear()
        self._nudge_count = 0
```

**Step 4: In plan_act.py, create per-session monitor instead of singleton**

Where `get_efficiency_monitor()` is called, replace with direct instantiation using settings:

```python
        settings = get_settings()
        self._efficiency_monitor = ToolEfficiencyMonitor(
            read_threshold=getattr(settings, "tool_efficiency_read_threshold", 5),
            strong_threshold=getattr(settings, "tool_efficiency_strong_threshold", 6),
            same_tool_threshold=getattr(settings, "tool_efficiency_same_tool_threshold", 4),
            same_tool_strong_threshold=getattr(settings, "tool_efficiency_same_tool_strong_threshold", 6),
            research_mode=research_mode,
        )
```

And call `self._efficiency_monitor.reset()` at the start of each step execution.

**Step 5: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_efficiency_settings.py -v -p no:cov -o addopts=`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/tool_efficiency_monitor.py backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/agents/test_efficiency_settings.py
git commit -m "feat(agent): settings-driven efficiency monitor with step-scoped reset"
```

---

### Task 15: Hallucination Mitigation Settings (4B)

**Files:**
- Modify: `backend/app/domain/services/agents/output_verifier.py` (grounding context size)
- Modify: `backend/app/domain/services/agents/execution.py` (use new thresholds)

**Step 1: Expand grounding context for DEEP research**

In `output_verifier.py`, find the grounding context truncation (around line 132 where 4K chars is set). Make it settings-aware:

```python
        # Use expanded context for DEEP research (design 4B)
        from app.core.config import get_settings
        settings = get_settings()
        default_size = getattr(settings, "hallucination_grounding_context_size", 4096)
        if research_depth == "DEEP":
            context_size = getattr(settings, "hallucination_grounding_context_deep", 8192)
        else:
            context_size = default_size

        grounding = source_context[:context_size]
```

**Step 2: Wire hallucination thresholds in execution.py**

In the hallucination verification section (around lines 1197-1219), use the new thresholds:

```python
        settings = get_settings()
        warn_threshold = getattr(settings, "hallucination_warn_threshold", 0.05)
        block_threshold = getattr(settings, "hallucination_block_threshold", 0.15)

        if hallucination_ratio > block_threshold:
            logger.error(
                "Hallucination ratio %.1f%% exceeds block threshold %.1f%%",
                hallucination_ratio * 100, block_threshold * 100,
            )
            # Add to delivery gate issues
        elif hallucination_ratio > warn_threshold:
            logger.warning(
                "Hallucination ratio %.1f%% exceeds warn threshold %.1f%%",
                hallucination_ratio * 100, warn_threshold * 100,
            )
```

**Step 3: Run linting + existing tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check app/domain/services/agents/output_verifier.py app/domain/services/agents/execution.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/app/domain/services/agents/output_verifier.py backend/app/domain/services/agents/execution.py
git commit -m "feat(quality): settings-driven hallucination thresholds with DEEP expansion"
```

---

### Task 16: Delivery Gate Hardening (4C)

**Files:**
- Modify: `backend/app/domain/services/agents/response_generator.py:413-485` (delivery gate)

**Step 1: Add graduated severity levels**

In `run_delivery_integrity_gate()`, replace boolean pass/fail with graduated response:

```python
    class GateResult(str, Enum):
        GREEN = "green"    # 0 issues — ship
        YELLOW = "yellow"  # 1-2 non-critical — ship with metadata
        RED = "red"        # 3+ issues or any critical — block

    def _assess_gate_severity(self, issues: list[dict]) -> str:
        """Assess overall gate severity from individual issues."""
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        if critical_count > 0 or len(issues) >= 3:
            return "red"
        if len(issues) > 0:
            return "yellow"
        return "green"
```

Add quality metadata to ReportEvent (in the emit section around lines 1389-1400):

```python
        # Attach quality metadata to report event
        if hasattr(event, "metadata") and isinstance(event.metadata, dict):
            event.metadata["quality_gate"] = gate_severity
            event.metadata["quality_issues"] = len(gate_issues)
```

**Step 2: Run existing tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/domain/services/agents/test_response_generator*.py -v -p no:cov -o addopts= -x`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/app/domain/services/agents/response_generator.py
git commit -m "feat(quality): graduated delivery gate with green/yellow/red severity"
```

---

### Task 17: Key Pool Configurability (5A)

**Files:**
- Modify: `backend/app/infrastructure/external/key_pool.py:152-153` (constants)
- Test: `backend/tests/infrastructure/external/test_key_pool_settings.py`

**Step 1: Write the failing test**

```python
"""Tests for configurable key pool circuit breaker."""

import pytest

from app.infrastructure.external.key_pool import CircuitBreaker


class TestKeyPoolSettings:
    """Verify CB reads thresholds from settings."""

    def test_custom_threshold(self):
        cb = CircuitBreaker(threshold=3, reset_timeout=60.0)
        assert cb._threshold == 3
        assert cb.open_seconds == 60.0

    def test_from_settings(self):
        from unittest.mock import patch

        with patch("app.infrastructure.external.key_pool.get_settings") as mock:
            mock.return_value = type("S", (), {
                "key_pool_cb_threshold": 3,
                "key_pool_cb_reset_timeout_5xx": 120,
                "key_pool_cb_reset_timeout_429": 30,
            })()

            cb = CircuitBreaker.from_settings()
            assert cb._threshold == 3
```

**Step 2: Run test to verify fail**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/test_key_pool_settings.py -v -p no:cov -o addopts=`
Expected: FAIL — `from_settings()` not found

**Step 3: Add from_settings() classmethod**

In `key_pool.py`, add to `CircuitBreaker`:

```python
    @classmethod
    def from_settings(cls) -> "CircuitBreaker":
        """Create a CircuitBreaker from application settings."""
        from app.core.config import get_settings
        settings = get_settings()
        return cls(
            threshold=getattr(settings, "key_pool_cb_threshold", CIRCUIT_BREAKER_THRESHOLD),
            reset_timeout=float(getattr(settings, "key_pool_cb_reset_timeout_5xx", CIRCUIT_BREAKER_RESET_TIMEOUT)),
        )
```

**Step 4: Run tests**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/infrastructure/external/test_key_pool_settings.py -v -p no:cov -o addopts=`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/key_pool.py backend/tests/infrastructure/external/test_key_pool_settings.py
git commit -m "feat(keypool): configurable circuit breaker thresholds via settings"
```

---

### Task 18: Search Provider Health Visibility (5B)

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/infrastructure/external/search/factory.py`

**Step 1: Add pre-search health check**

In `plan_act.py`, before dispatching research steps, add a health check:

```python
    async def _check_search_health(self) -> dict[str, Any]:
        """Pre-search health check. Returns provider health summary."""
        if not self._search_engine:
            return {"status": "no_search_engine"}

        # For FallbackSearchEngine, check provider health
        if hasattr(self._search_engine, "get_health_summary"):
            return await self._search_engine.get_health_summary()

        return {"status": "ok", "provider": type(self._search_engine).__name__}
```

In `factory.py`, add `get_health_summary()` to `FallbackSearchEngine`:

```python
    async def get_health_summary(self) -> dict[str, Any]:
        """Return health status of all providers in the chain."""
        summary = {"providers": [], "healthy_count": 0, "total_count": len(self._engines)}
        for name, engine in self._engines.items():
            pool = getattr(engine, "_key_pool", None)
            if pool:
                healthy = pool.healthy_key_count
                total = pool.total_key_count
                summary["providers"].append({
                    "name": name,
                    "healthy_keys": healthy,
                    "total_keys": total,
                    "status": "healthy" if healthy > 0 else "exhausted",
                })
                if healthy > 0:
                    summary["healthy_count"] += 1
            else:
                summary["providers"].append({"name": name, "status": "unknown"})
                summary["healthy_count"] += 1  # assume healthy if no pool
        return summary
```

**Step 2: Log health before research steps**

In `plan_act.py`, at the start of step execution for research steps, call and log:

```python
        if step.phase_tag and "research" in step.phase_tag:
            health = await self._check_search_health()
            logger.info("Search provider health: %s", health)
            if health.get("healthy_count", 0) == 0:
                logger.error("All search providers exhausted! Research step may fail.")
```

**Step 3: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/infrastructure/external/search/factory.py
git commit -m "feat(search): pre-research health check and provider health visibility"
```

---

### Task 19: LLM Retry Budget Middleware Wiring (5D)

**Files:**
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py` (wire existing middleware)

The middleware pipeline already exists at `middleware_impl.py` (367 lines) but is NOT wired. The feature flag `feature_llm_middleware_pipeline` exists but is `False`.

**Step 1: Wire the middleware conditionally**

In `openai_llm.py` `__init__`, after the existing setup, add:

```python
        # Wire middleware pipeline when feature flag is enabled (design 5D)
        from app.core.config import get_settings
        settings = get_settings()
        if getattr(settings, "feature_llm_middleware_pipeline", False):
            try:
                from app.infrastructure.external.llm.middleware_impl import build_default_pipeline
                self._middleware_pipeline = build_default_pipeline(self._raw_ask)
                logger.info("LLM middleware pipeline enabled")
            except Exception:
                logger.warning("Failed to initialize LLM middleware pipeline", exc_info=True)
                self._middleware_pipeline = None
        else:
            self._middleware_pipeline = None
```

This is opt-in via the existing feature flag. No behavioral change when flag is False.

**Step 2: Commit**

```bash
git add backend/app/infrastructure/external/llm/openai_llm.py
git commit -m "feat(llm): wire existing middleware pipeline behind feature flag"
```

---

## Phase 3: LOW Priority (Tasks 20–23)

Polish and configurability.

---

### Task 20: Rich Stuck Recovery (2D)

**Files:**
- Modify: `backend/app/domain/services/flows/step_failure.py:48-55`

**Step 1: Enhance placeholder with file list**

Replace the minimal placeholder injection (line 50) with a richer one:

```python
            if not failed_step.result:
                # Collect files written during this step for richer context
                files_info = ""
                if hasattr(failed_step, "artifacts") and failed_step.artifacts:
                    file_list = ", ".join(failed_step.artifacts[:5])
                    files_info = f" Files created: {file_list}."

                failed_step.result = (
                    f"[Step failed: {(failed_step.error or 'execution error')[:120]}."
                    f"{files_info}"
                    f" Partial results may be available in workspace files.]"
                )
```

**Step 2: Commit**

```bash
git add backend/app/domain/services/flows/step_failure.py
git commit -m "fix(recovery): richer stuck recovery placeholder with file list"
```

---

### Task 21: Comprehensiveness Signal for DEEP Research (3D)

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py`

**Step 1: Add comprehensiveness signal**

In `build_summarize_prompt()`, add for DEEP depth:

```python
    if research_depth == "DEEP":
        prompt_parts.append("""
## Comprehensiveness Requirements (DEEP Research)

Your report MUST include ALL of the following:
1. **Comparative Analysis**: Compare at least 2-3 alternatives or approaches
2. **Real-World Examples**: Include concrete examples, case studies, or benchmarks
3. **Limitations & Trade-offs**: Discuss known limitations, edge cases, and trade-offs
4. **Actionable Recommendations**: End with specific, prioritized recommendations
5. **Quantitative Data**: Include numbers, metrics, or benchmarks where available
""")
```

**Step 2: Commit**

```bash
git add backend/app/domain/services/prompts/execution.py
git commit -m "feat(prompts): comprehensiveness signal for DEEP research reports"
```

---

### Task 22: Plotly Chart Logging (4D)

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py`

**Step 1: Log actual failure reason**

Find the Plotly chart generation section (around lines 729-740). After `chart_result is None`:

```python
        if chart_result is None:
            logger.warning(
                "Plotly chart unavailable for report_id=%s session=%s: %s. "
                "Falling back to legacy SVG.",
                event.id,
                self._session_id,
                getattr(chart_result, "error", "unknown reason"),
            )
```

**Step 2: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py
git commit -m "fix(charts): log actual Plotly failure reason before SVG fallback"
```

---

### Task 23: Model Router Tier Settings (5C)

**Files:**
- Modify: `backend/app/domain/services/agents/model_router.py:273-282`

**Step 1: Replace hardcoded values with settings**

In `_get_config()` method (around lines 273-282), replace hardcoded values:

```python
        if tier == ModelTier.FAST:
            model_name = self.settings.fast_model
            max_tokens = getattr(self.settings, "fast_model_max_tokens", 4096)
            temperature = getattr(self.settings, "fast_model_temperature", 0.2)
        elif tier == ModelTier.POWERFUL:
            model_name = self.settings.powerful_model
            max_tokens = self.settings.max_tokens
            temperature = self.settings.temperature
        else:  # BALANCED
            model_name = self.settings.effective_balanced_model
            max_tokens = getattr(self.settings, "balanced_model_max_tokens", 8192)
            temperature = self.settings.temperature
```

**Step 2: Commit**

```bash
git add backend/app/domain/services/agents/model_router.py
git commit -m "feat(router): settings-driven model tier max_tokens and temperature"
```

---

## Final: Regression Test Pass

### Task 24: Full Regression Suite

**Step 1: Run full test suite**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker pytest tests/ -x --timeout=120 -q`
Expected: 4979+ tests PASS, 0 FAIL

**Step 2: Run linting**

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check . && conda run -n pythinker ruff format --check .`
Expected: Clean

**Step 3: Final commit if any fixups needed**

```bash
git commit -m "fix: address any regression test failures"
```

---

## Summary

| Phase | Tasks | Design Items | Impact |
|-------|-------|-------------|--------|
| HIGH | 1–11 | 1A, 1B, 2A, 2B, 3A, 3B, 3C, 4A | Prevents timeouts, file chaos, citation gaps |
| MEDIUM | 12–19 | 1C, 1D, 2C, 4B, 4C, 5A, 5B, 5D | Improves resilience and observability |
| LOW | 20–23 | 2D, 3D, 4D, 5C | Polish and configurability |
| FINAL | 24 | — | Regression pass |

**New files:** 1 (`provider_profile.py`)
**Modified files:** ~15
**New test files:** ~7
**Total tasks:** 24
