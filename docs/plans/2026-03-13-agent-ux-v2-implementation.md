# Agent UX v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship professional browser choreography (Chrome UI in screencast, human-like cursor/typing/dwell), xterm.js live terminal, smarter agent shell usage, and skill-driven agent architecture — all in a single unified release.

**Architecture:** Backend-driven choreography — all timing, cursor animation, and skill orchestration in the backend. Frontend consumes structured SSE events and JPEG frames. New `BrowserChoreographer` wraps `PlaywrightBrowser` actions. `SkillMatcher` auto-detects skills before planning. `TerminalLiveView.vue` replaces static polling with xterm.js.

**Tech Stack:** Python 3.12, FastAPI, Playwright, CDP, Vue 3 Composition API, xterm.js 6 (@xterm/xterm), Pinia, SSE

**Design doc:** `docs/plans/2026-03-13-agent-ux-v2-design.md`

---

## Task 1: Feature Flags & Config

**Files:**
- Modify: `backend/app/core/config_features.py` (add flags to `FeatureFlagsSettingsMixin`)
- Modify: `sandbox/app/core/config.py` (add screencast settings)
- Test: `backend/tests/core/test_config_features.py` (verify flag defaults)

**Step 1: Add backend feature flags**

In `backend/app/core/config_features.py`, add to `FeatureFlagsSettingsMixin`:

```python
# Browser Choreography (Agent UX v2)
browser_choreography_enabled: bool = True
browser_choreography_profile: str = "professional"  # fast/professional/cinematic
browser_screencast_include_chrome_ui: bool = True

# Terminal Enhancement (Agent UX v2)
terminal_live_streaming_enabled: bool = True
terminal_mastery_prompt_enabled: bool = True
terminal_proactive_preference_enabled: bool = True

# Skill-Driven Architecture (Agent UX v2)
skill_auto_detection_enabled: bool = True
skill_auto_detection_threshold: float = 0.6
skill_first_planning_enabled: bool = True
skill_ui_events_enabled: bool = True
```

**Step 2: Add sandbox screencast settings**

In `sandbox/app/core/config.py`, add to the `Settings` class:

```python
# Screencast dimensions (Agent UX v2)
SCREENCAST_INCLUDE_CHROME_UI: bool = True
SCREENCAST_MAX_HEIGHT: int = 1024  # 1024 = full window with Chrome UI, 900 = viewport only
```

**Step 3: Write test for flag defaults**

```python
# backend/tests/core/test_config_ux_v2_flags.py
from app.core.config import get_settings


def test_browser_choreography_defaults():
    settings = get_settings()
    assert settings.browser_choreography_enabled is True
    assert settings.browser_choreography_profile == "professional"
    assert settings.browser_screencast_include_chrome_ui is True


def test_terminal_enhancement_defaults():
    settings = get_settings()
    assert settings.terminal_live_streaming_enabled is True
    assert settings.terminal_mastery_prompt_enabled is True
    assert settings.terminal_proactive_preference_enabled is True


def test_skill_architecture_defaults():
    settings = get_settings()
    assert settings.skill_auto_detection_enabled is True
    assert settings.skill_auto_detection_threshold == 0.6
    assert settings.skill_first_planning_enabled is True
    assert settings.skill_ui_events_enabled is True
```

**Step 4: Run tests**

```bash
cd backend && conda activate pythinker
pytest tests/core/test_config_ux_v2_flags.py -v
```

Expected: PASS (3 tests)

**Step 5: Lint**

```bash
ruff check backend/app/core/config_features.py sandbox/app/core/config.py
ruff format backend/app/core/config_features.py sandbox/app/core/config.py
```

**Step 6: Commit**

```bash
git add backend/app/core/config_features.py sandbox/app/core/config.py backend/tests/core/test_config_ux_v2_flags.py
git commit -m "feat(config): add Agent UX v2 feature flags for choreography, terminal, skills"
```

---

## Task 2: Browser Choreography Engine

**Files:**
- Create: `backend/app/infrastructure/external/browser/choreography.py`
- Test: `backend/tests/infrastructure/browser/test_choreography.py`

**Step 1: Write failing tests**

```python
# backend/tests/infrastructure/browser/test_choreography.py
import pytest
from app.infrastructure.external.browser.choreography import (
    BrowserChoreographer,
    ChoreographyProfile,
    PROFILES,
)


def test_profiles_exist():
    assert "fast" in PROFILES
    assert "professional" in PROFILES
    assert "cinematic" in PROFILES


def test_professional_profile_dwell():
    p = PROFILES["professional"]
    assert 5.0 <= p.dwell_after_navigate <= 10.0


def test_fast_profile_minimal_delays():
    p = PROFILES["fast"]
    assert p.dwell_after_navigate <= 1.5
    assert p.typing_delay_ms <= 15


def test_cinematic_profile_slow_cursor():
    p = PROFILES["cinematic"]
    assert p.cursor_move_steps >= 30
    assert p.cursor_move_duration >= 1.0


def test_choreographer_init_with_profile_name():
    c = BrowserChoreographer(profile_name="professional")
    assert c.profile.name == "professional"
    assert c.enabled is True


def test_choreographer_disabled():
    c = BrowserChoreographer(profile_name="professional", enabled=False)
    assert c.enabled is False


def test_choreographer_unknown_profile_falls_back():
    c = BrowserChoreographer(profile_name="nonexistent")
    assert c.profile.name == "professional"  # fallback to professional


@pytest.mark.asyncio
async def test_choreographer_navigate_delay():
    """When enabled, navigate_pre_extract_delay returns the dwell time."""
    c = BrowserChoreographer(profile_name="fast")
    delay = c.get_navigate_dwell()
    assert delay == PROFILES["fast"].dwell_after_navigate


@pytest.mark.asyncio
async def test_choreographer_disabled_returns_zero_dwell():
    c = BrowserChoreographer(profile_name="professional", enabled=False)
    assert c.get_navigate_dwell() == 0.0


def test_choreographer_get_click_params():
    c = BrowserChoreographer(profile_name="professional")
    params = c.get_click_params()
    assert params["hover_pause"] == PROFILES["professional"].hover_before_click
    assert params["cursor_steps"] == PROFILES["professional"].cursor_move_steps
    assert params["settle_pause"] == PROFILES["professional"].post_click_settle


def test_choreographer_get_type_delay_ms():
    c = BrowserChoreographer(profile_name="cinematic")
    assert c.get_type_delay_ms() == PROFILES["cinematic"].typing_delay_ms


def test_choreographer_get_scroll_pause():
    c = BrowserChoreographer(profile_name="professional")
    assert c.get_scroll_pause() == PROFILES["professional"].scroll_step_pause
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/browser/test_choreography.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.external.browser.choreography'`

**Step 3: Write implementation**

```python
# backend/app/infrastructure/external/browser/choreography.py
"""Browser interaction choreography engine.

Wraps browser actions with human-like timing profiles for professional
visual feedback in CDP screencast. Three profiles: fast (development),
professional (production default), cinematic (demos/presentations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChoreographyProfile:
    """Timing profile for browser interactions."""

    name: str
    dwell_after_navigate: float  # seconds to pause after page load (user sees the page)
    hover_before_click: float  # hover pause before clicking
    cursor_move_steps: int  # Playwright mouse.move() subdivisions for smooth travel
    cursor_move_duration: float  # total cursor travel time (informational)
    typing_delay_ms: int  # per-character delay (Playwright delay= param)
    scroll_step_pause: float  # between scroll increments
    post_click_settle: float  # after click, let page react visibly
    post_type_pause: float  # after finishing typing
    pre_action_pause: float  # brief pause before any action


PROFILES: dict[str, ChoreographyProfile] = {
    "fast": ChoreographyProfile(
        name="fast",
        dwell_after_navigate=1.0,
        hover_before_click=0.1,
        cursor_move_steps=5,
        cursor_move_duration=0.15,
        typing_delay_ms=10,
        scroll_step_pause=0.3,
        post_click_settle=0.3,
        post_type_pause=0.1,
        pre_action_pause=0.05,
    ),
    "professional": ChoreographyProfile(
        name="professional",
        dwell_after_navigate=7.0,
        hover_before_click=0.4,
        cursor_move_steps=20,
        cursor_move_duration=0.6,
        typing_delay_ms=65,
        scroll_step_pause=0.8,
        post_click_settle=1.5,
        post_type_pause=0.5,
        pre_action_pause=0.3,
    ),
    "cinematic": ChoreographyProfile(
        name="cinematic",
        dwell_after_navigate=10.0,
        hover_before_click=0.8,
        cursor_move_steps=40,
        cursor_move_duration=1.2,
        typing_delay_ms=100,
        scroll_step_pause=1.2,
        post_click_settle=2.5,
        post_type_pause=1.0,
        pre_action_pause=0.5,
    ),
}

DEFAULT_PROFILE = "professional"


class BrowserChoreographer:
    """Controls timing and visual choreography for browser actions.

    Injected into PlaywrightBrowser to wrap navigate/click/type/scroll
    with human-like delays. When disabled, all timing methods return
    zero/minimal values so the browser operates at machine speed.
    """

    def __init__(self, profile_name: str = DEFAULT_PROFILE, enabled: bool = True) -> None:
        self.enabled = enabled
        if profile_name not in PROFILES:
            logger.warning(
                "Unknown choreography profile '%s', falling back to '%s'",
                profile_name,
                DEFAULT_PROFILE,
            )
            profile_name = DEFAULT_PROFILE
        self.profile = PROFILES[profile_name]

    def get_navigate_dwell(self) -> float:
        """Seconds to dwell on page after navigation before extracting content."""
        return self.profile.dwell_after_navigate if self.enabled else 0.0

    def get_click_params(self) -> dict[str, Any]:
        """Parameters for click choreography."""
        if not self.enabled:
            return {
                "hover_pause": 0.0,
                "cursor_steps": 1,
                "settle_pause": 0.0,
                "pre_pause": 0.0,
            }
        return {
            "hover_pause": self.profile.hover_before_click,
            "cursor_steps": self.profile.cursor_move_steps,
            "settle_pause": self.profile.post_click_settle,
            "pre_pause": self.profile.pre_action_pause,
        }

    def get_type_delay_ms(self) -> int:
        """Per-character typing delay in milliseconds."""
        return self.profile.typing_delay_ms if self.enabled else 10

    def get_post_type_pause(self) -> float:
        """Seconds to pause after finishing typing."""
        return self.profile.post_type_pause if self.enabled else 0.0

    def get_scroll_pause(self) -> float:
        """Seconds to pause between scroll increments."""
        return self.profile.scroll_step_pause if self.enabled else 0.3

    def get_pre_action_pause(self) -> float:
        """Brief pause before any browser action."""
        return self.profile.pre_action_pause if self.enabled else 0.0
```

**Step 4: Run tests**

```bash
pytest tests/infrastructure/browser/test_choreography.py -v
```

Expected: PASS (12 tests)

**Step 5: Lint**

```bash
ruff check backend/app/infrastructure/external/browser/choreography.py
ruff format backend/app/infrastructure/external/browser/choreography.py
```

**Step 6: Commit**

```bash
git add backend/app/infrastructure/external/browser/choreography.py backend/tests/infrastructure/browser/test_choreography.py
git commit -m "feat(browser): add BrowserChoreographer with fast/professional/cinematic timing profiles"
```

---

## Task 3: Inject Choreographer into PlaywrightBrowser

**Files:**
- Modify: `backend/app/infrastructure/external/browser/playwright_browser.py` (lines ~33-36, ~2377, ~2971, ~3069, ~3192, ~3234)
- Modify: `backend/app/infrastructure/external/browser/connection_pool.py` (line ~485)
- Test: `backend/tests/infrastructure/browser/test_playwright_choreography_integration.py`

**Step 1: Write integration test**

```python
# backend/tests/infrastructure/browser/test_playwright_choreography_integration.py
"""Test that PlaywrightBrowser accepts and uses BrowserChoreographer."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.infrastructure.external.browser.choreography import BrowserChoreographer


def test_playwright_browser_accepts_choreographer():
    """PlaywrightBrowser.__init__ accepts optional choreographer param."""
    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    choreographer = BrowserChoreographer(profile_name="fast")
    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222", choreographer=choreographer)
    assert browser._choreographer is choreographer
    assert browser._choreographer.profile.name == "fast"


def test_playwright_browser_creates_default_choreographer():
    """Without explicit choreographer, one is created from settings."""
    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
    assert browser._choreographer is not None
    assert browser._choreographer.enabled is True
```

**Step 2: Run to verify failure**

```bash
pytest tests/infrastructure/browser/test_playwright_choreography_integration.py -v
```

Expected: FAIL — `PlaywrightBrowser.__init__` doesn't accept `choreographer` param

**Step 3: Modify PlaywrightBrowser.__init__**

In `playwright_browser.py`, add import at top:

```python
from app.infrastructure.external.browser.choreography import BrowserChoreographer
```

Add `choreographer` parameter to `__init__()` and store it:

```python
def __init__(
    self,
    cdp_url: str,
    block_resources: bool = False,
    randomize_fingerprint: bool = False,
    choreographer: BrowserChoreographer | None = None,
) -> None:
    # ... existing init code ...
    settings = get_settings()
    if choreographer is not None:
        self._choreographer = choreographer
    else:
        self._choreographer = BrowserChoreographer(
            profile_name=settings.browser_choreography_profile,
            enabled=settings.browser_choreography_enabled,
        )
```

**Step 4: Modify navigate() — add dwell after page load**

In `navigate()` (or `_navigate_impl()`), after the `page.goto()` and `wait_until` succeeds, before content extraction:

```python
# Choreography: dwell on page so user can see it in screencast
dwell = self._choreographer.get_navigate_dwell()
if dwell > 0:
    logger.debug("Choreography: dwelling %.1fs on %s", dwell, url)
    await asyncio.sleep(dwell)
```

**Step 5: Modify click() — smooth cursor movement + hover + settle**

Replace the existing `asyncio.sleep(0.3)` after scroll and `_show_cursor_click()` with choreographed flow:

```python
# Choreography: smooth cursor movement to target
click_params = self._choreographer.get_click_params()
pre_pause = click_params["pre_pause"]
if pre_pause > 0:
    await asyncio.sleep(pre_pause)

# Move cursor smoothly to click target (visible in screencast)
target_x, target_y = element_center_x, element_center_y
await self.page.mouse.move(target_x, target_y, steps=click_params["cursor_steps"])

# Hover pause (element hover state visible in screencast)
hover_pause = click_params["hover_pause"]
if hover_pause > 0:
    await asyncio.sleep(hover_pause)

# Execute click
await element.click(timeout=timeout)

# Post-click settle (let page react visibly)
settle_pause = click_params["settle_pause"]
if settle_pause > 0:
    await asyncio.sleep(settle_pause)
```

**Step 6: Modify input() — realistic typing speed**

Replace the hardcoded `delay=10` in `keyboard.type()`:

```python
typing_delay = self._choreographer.get_type_delay_ms()
await self.page.keyboard.type(text, delay=typing_delay)

# Post-type pause
post_pause = self._choreographer.get_post_type_pause()
if post_pause > 0:
    await asyncio.sleep(post_pause)
```

**Step 7: Modify scroll_up()/scroll_down() — paced scrolling**

Replace hardcoded `asyncio.sleep(0.3)` / `asyncio.sleep(0.35)`:

```python
scroll_pause = self._choreographer.get_scroll_pause()
await asyncio.sleep(scroll_pause)
```

**Step 8: Modify connection_pool.py — pass choreographer**

At `connection_pool.py` line ~485, update `PlaywrightBrowser` instantiation:

```python
from app.infrastructure.external.browser.choreography import BrowserChoreographer

choreographer = BrowserChoreographer(
    profile_name=settings.browser_choreography_profile,
    enabled=settings.browser_choreography_enabled,
)
browser = PlaywrightBrowser(
    cdp_url=cdp_url,
    block_resources=block_resources,
    randomize_fingerprint=randomize_fingerprint,
    choreographer=choreographer,
)
```

**Step 9: Run tests**

```bash
pytest tests/infrastructure/browser/test_playwright_choreography_integration.py -v
pytest tests/infrastructure/browser/test_choreography.py -v
```

Expected: ALL PASS

**Step 10: Lint and commit**

```bash
ruff check backend/app/infrastructure/external/browser/playwright_browser.py backend/app/infrastructure/external/browser/connection_pool.py
ruff format backend/app/infrastructure/external/browser/playwright_browser.py backend/app/infrastructure/external/browser/connection_pool.py
git add backend/app/infrastructure/external/browser/playwright_browser.py backend/app/infrastructure/external/browser/connection_pool.py backend/tests/infrastructure/browser/test_playwright_choreography_integration.py
git commit -m "feat(browser): inject BrowserChoreographer into PlaywrightBrowser actions"
```

---

## Task 4: Screencast — Include Chrome UI (Address Bar)

**Files:**
- Modify: `sandbox/app/services/cdp_screencast.py` (lines 61-73, 452-484)
- Modify: `sandbox/app/api/v1/screencast.py` (lines ~191, ~472)
- Modify: `sandbox/app/core/config.py`
- Modify: `frontend/src/types/liveViewer.ts` (lines 235-237)
- Modify: `frontend/src/components/SandboxViewer.vue` (forceDimensionReset if present)
- Test: Manual — rebuild sandbox, verify address bar visible in screencast

**Step 1: Update ScreencastConfig defaults**

In `sandbox/app/services/cdp_screencast.py`, line 67-70:

```python
# Before:
max_height: int = 900   # Match Playwright DEFAULT_VIEWPORT height

# After:
max_height: int = 1024  # Full window including Chrome UI (address bar, tab strip)
```

**Step 2: Make _ensure_viewport conditional**

In `_ensure_viewport()` (line 452), check the new setting:

```python
async def _ensure_viewport(self) -> None:
    """Set viewport via CDP — skip when showing full Chrome UI."""
    if self._viewport_set:
        return
    if not self._ws or self._ws.closed:
        return
    # When showing Chrome UI, don't override device metrics —
    # let the browser render naturally at its window size
    from app.core.config import settings
    if settings.SCREENCAST_INCLUDE_CHROME_UI:
        self._viewport_set = True
        return
    result = await self._send_command(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": self.config.max_width,
            "height": self.config.max_height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )
    if result and "error" not in result:
        self._viewport_set = True
```

**Step 3: Thread max_height from config to ScreencastConfig**

In `sandbox/app/api/v1/screencast.py`, update both instantiation sites (~line 191 and ~472):

```python
from app.core.config import settings

# In stream_frames_ws:
service = CDPScreencastService(
    ScreencastConfig(
        format="jpeg",
        quality=quality,
        max_height=settings.SCREENCAST_MAX_HEIGHT,
    )
)

# In generate_mjpeg:
service = CDPScreencastService(
    ScreencastConfig(
        format="jpeg",
        quality=quality,
        max_height=settings.SCREENCAST_MAX_HEIGHT,
    )
)
```

**Step 4: Update frontend constants**

In `frontend/src/types/liveViewer.ts`, lines 235-237:

```typescript
// Before:
export const SANDBOX_HEIGHT = 900

// After:
export const SANDBOX_HEIGHT = 1024
```

**Step 5: Update forceDimensionReset calls (if any)**

Search for any `forceDimensionReset(1280, 900)` in `SandboxViewer.vue` or `KonvaLiveStage.vue` and change to `forceDimensionReset(1280, 1024)`. The composable `useKonvaScreencast.ts` auto-detects frame dimensions from the JPEG `ImageBitmap`, so it will self-correct when real frames arrive — but the initial seed should match.

**Step 6: Lint frontend**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 7: Commit**

```bash
git add sandbox/app/services/cdp_screencast.py sandbox/app/api/v1/screencast.py sandbox/app/core/config.py frontend/src/types/liveViewer.ts frontend/src/components/SandboxViewer.vue
git commit -m "feat(screencast): include Chrome UI (address bar) in CDP screencast frames"
```

**Step 8: Rebuild sandbox image**

```bash
docker compose build --no-cache sandbox
```

**Verification:** Start the stack, open a session, navigate to a URL. The screencast should show Chrome's address bar, tab strip, and the page content below.

---

## Task 5: SkillEvent — New SSE Event Type

**Files:**
- Modify: `backend/app/domain/models/event.py`
- Test: `backend/tests/domain/models/test_skill_event.py`

**Step 1: Write failing test**

```python
# backend/tests/domain/models/test_skill_event.py
from app.domain.models.event import SkillEvent


def test_skill_event_creation():
    event = SkillEvent(
        skill_id="research-v1",
        skill_name="Research",
        action="activated",
        reason="Detected research task patterns",
    )
    assert event.type == "skill"
    assert event.skill_id == "research-v1"
    assert event.action == "activated"
    assert event.tools_affected is None


def test_skill_event_with_tools():
    event = SkillEvent(
        skill_id="coding-v1",
        skill_name="Coding",
        action="activated",
        reason="Step requires code execution",
        tools_affected=["shell_exec", "code_execute", "file_write"],
    )
    assert len(event.tools_affected) == 3


def test_skill_event_deactivated():
    event = SkillEvent(
        skill_id="research-v1",
        skill_name="Research",
        action="deactivated",
        reason="Step completed",
    )
    assert event.action == "deactivated"


def test_skill_event_serialization():
    event = SkillEvent(
        skill_id="browser-v1",
        skill_name="Browser Automation",
        action="matched",
        reason="URL pattern detected",
    )
    data = event.model_dump()
    assert data["type"] == "skill"
    assert "id" in data
    assert "timestamp" in data
```

**Step 2: Run to verify failure**

```bash
pytest tests/domain/models/test_skill_event.py -v
```

Expected: FAIL — `ImportError: cannot import name 'SkillEvent'`

**Step 3: Add SkillEvent to event.py**

In `backend/app/domain/models/event.py`, add after the other event classes:

```python
class SkillEvent(BaseEvent):
    """Emitted when a skill is activated, deactivated, or matched."""

    type: Literal["skill"] = "skill"
    skill_id: str
    skill_name: str
    action: Literal["activated", "deactivated", "matched"]
    reason: str
    tools_affected: list[str] | None = None
```

**Step 4: Run tests**

```bash
pytest tests/domain/models/test_skill_event.py -v
```

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/app/domain/models/event.py backend/tests/domain/models/test_skill_event.py
git commit -m "feat(events): add SkillEvent for user-visible skill activation feedback"
```

---

## Task 6: SkillMatcher — Auto-Detection Service

**Files:**
- Create: `backend/app/domain/services/skill_matcher.py`
- Test: `backend/tests/domain/services/test_skill_matcher.py`

**Step 1: Write failing tests**

```python
# backend/tests/domain/services/test_skill_matcher.py
import pytest
from app.domain.services.skill_matcher import SkillMatcher, SkillMatch
from app.domain.models.skill import Skill, SkillCategory, SkillSource, SkillInvocationType


def _make_skill(
    skill_id: str,
    name: str,
    category: SkillCategory,
    trigger_patterns: list[str] | None = None,
    required_tools: list[str] | None = None,
) -> Skill:
    """Helper to build test skills."""
    return Skill(
        id=skill_id,
        name=name,
        description=f"Test {name} skill",
        category=category,
        source=SkillSource.OFFICIAL,
        invocation_type=SkillInvocationType.AI,
        trigger_patterns=trigger_patterns or [],
        required_tools=required_tools or [],
    )


RESEARCH_SKILL = _make_skill(
    "research-v1",
    "Research",
    SkillCategory.RESEARCH,
    trigger_patterns=[r"research\b", r"find\s+information", r"look\s+up", r"search\s+for"],
    required_tools=["search", "browser_navigate"],
)

CODING_SKILL = _make_skill(
    "coding-v1",
    "Coding",
    SkillCategory.CODING,
    trigger_patterns=[r"write\s+(a\s+)?code", r"implement", r"build\s+a", r"create\s+a\s+(script|program)"],
    required_tools=["shell_exec", "code_execute", "file_write"],
)

BROWSER_SKILL = _make_skill(
    "browser-v1",
    "Browser Automation",
    SkillCategory.BROWSER,
    trigger_patterns=[r"browse\s+to", r"open\s+(the\s+)?website", r"navigate\s+to", r"go\s+to\s+https?://"],
    required_tools=["browser_navigate", "browser_click"],
)

ALL_SKILLS = [RESEARCH_SKILL, CODING_SKILL, BROWSER_SKILL]


class TestSkillMatcher:
    def setup_method(self):
        self.matcher = SkillMatcher()

    def test_match_research_query(self):
        matches = self.matcher.match("Research the latest AI trends", ALL_SKILLS)
        assert len(matches) >= 1
        assert matches[0].skill.id == "research-v1"
        assert matches[0].confidence >= 0.6

    def test_match_coding_query(self):
        matches = self.matcher.match("Implement a REST API endpoint", ALL_SKILLS)
        assert len(matches) >= 1
        assert any(m.skill.id == "coding-v1" for m in matches)

    def test_match_browser_query(self):
        matches = self.matcher.match("Navigate to https://example.com", ALL_SKILLS)
        assert len(matches) >= 1
        assert any(m.skill.id == "browser-v1" for m in matches)

    def test_no_match_irrelevant_query(self):
        matches = self.matcher.match("Hello, how are you?", ALL_SKILLS, threshold=0.6)
        assert len(matches) == 0

    def test_threshold_filtering(self):
        matches_low = self.matcher.match("Research AI", ALL_SKILLS, threshold=0.3)
        matches_high = self.matcher.match("Research AI", ALL_SKILLS, threshold=0.9)
        assert len(matches_low) >= len(matches_high)

    def test_matches_sorted_by_confidence(self):
        matches = self.matcher.match(
            "Research and implement a web scraper", ALL_SKILLS, threshold=0.1
        )
        if len(matches) >= 2:
            assert matches[0].confidence >= matches[1].confidence

    def test_empty_skills_list(self):
        matches = self.matcher.match("Research AI", [])
        assert matches == []

    def test_empty_message(self):
        matches = self.matcher.match("", ALL_SKILLS)
        assert matches == []

    def test_skill_match_has_reason(self):
        matches = self.matcher.match("Research the latest AI trends", ALL_SKILLS)
        assert len(matches) >= 1
        assert matches[0].reason  # non-empty reason string
```

**Step 2: Run to verify failure**

```bash
pytest tests/domain/services/test_skill_matcher.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/app/domain/services/skill_matcher.py
"""Skill auto-detection from user messages.

Matches user messages against skill trigger patterns (regex)
and keyword overlap to identify relevant skills before planning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.domain.models.skill import Skill

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """A matched skill with confidence and reason."""

    skill: Skill
    confidence: float
    reason: str


class SkillMatcher:
    """Matches user messages to relevant skills using trigger patterns."""

    def match(
        self,
        message: str,
        available_skills: list[Skill],
        threshold: float = 0.6,
    ) -> list[SkillMatch]:
        """Return skills matching the message, ranked by confidence descending."""
        if not message or not available_skills:
            return []

        matches: list[SkillMatch] = []
        message_lower = message.lower()

        for skill in available_skills:
            score, reason = self._compute_match_score(message_lower, skill)
            if score >= threshold:
                matches.append(SkillMatch(skill=skill, confidence=score, reason=reason))

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def _compute_match_score(self, message_lower: str, skill: Skill) -> tuple[float, str]:
        """Score a skill against a message. Returns (score, reason)."""
        score = 0.0
        reasons: list[str] = []

        # 1. Trigger pattern matches (highest signal: 0.7 per match, capped at 1.0)
        pattern_hits = 0
        for pattern in skill.trigger_patterns:
            try:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    pattern_hits += 1
            except re.error:
                logger.warning("Invalid trigger pattern '%s' in skill '%s'", pattern, skill.id)
                continue

        if pattern_hits > 0:
            pattern_score = min(1.0, pattern_hits * 0.7)
            score += pattern_score * 0.7  # 70% weight for pattern matches
            reasons.append(f"Matched {pattern_hits} trigger pattern(s)")

        # 2. Category keyword overlap (0.3 weight)
        category_keywords = self._category_keywords(skill)
        keyword_hits = sum(1 for kw in category_keywords if kw in message_lower)
        if keyword_hits > 0 and category_keywords:
            keyword_score = min(1.0, keyword_hits / max(len(category_keywords), 1))
            score += keyword_score * 0.3
            reasons.append(f"Matched {keyword_hits} category keyword(s)")

        reason = "; ".join(reasons) if reasons else "No match"
        return score, reason

    def _category_keywords(self, skill: Skill) -> list[str]:
        """Extract keywords from skill name, category, and description."""
        words: list[str] = []
        words.extend(skill.name.lower().split())
        words.append(skill.category.value.lower())
        # Add required tool names as keywords (e.g., "browser" from "browser_navigate")
        for tool in skill.required_tools:
            parts = tool.split("_")
            words.extend(parts)
        return list(set(words))
```

**Step 4: Run tests**

```bash
pytest tests/domain/services/test_skill_matcher.py -v
```

Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add backend/app/domain/services/skill_matcher.py backend/tests/domain/services/test_skill_matcher.py
git commit -m "feat(skills): add SkillMatcher for auto-detection from user messages"
```

---

## Task 7: Integrate SkillMatcher into PlanActFlow

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py` (around line ~2151)
- Modify: `backend/app/domain/services/agents/execution.py` (lines 316-367, add SkillEvent emission)
- Test: `backend/tests/domain/services/flows/test_plan_act_skill_matching.py`

**Step 1: Write test**

```python
# backend/tests/domain/services/flows/test_plan_act_skill_matching.py
"""Test that PlanActFlow auto-detects and injects skills before planning."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.domain.services.skill_matcher import SkillMatcher, SkillMatch
from app.domain.models.skill import Skill, SkillCategory, SkillSource, SkillInvocationType


def _make_skill(skill_id: str, name: str, patterns: list[str]) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        description=f"Test {name}",
        category=SkillCategory.RESEARCH,
        source=SkillSource.OFFICIAL,
        invocation_type=SkillInvocationType.AI,
        trigger_patterns=patterns,
        required_tools=[],
    )


class TestSkillAutoDetection:
    def test_matcher_integrates_with_skill_model(self):
        """SkillMatcher works with real Skill model objects."""
        matcher = SkillMatcher()
        skill = _make_skill("test-1", "Research", [r"research\b", r"find\s+info"])
        matches = matcher.match("Research the best frameworks", [skill])
        assert len(matches) == 1
        assert matches[0].skill.id == "test-1"

    def test_matched_skills_have_valid_ids(self):
        matcher = SkillMatcher()
        skills = [
            _make_skill("s1", "Research", [r"research"]),
            _make_skill("s2", "Coding", [r"implement"]),
        ]
        matches = matcher.match("Research and implement a solution", skills, threshold=0.3)
        ids = [m.skill.id for m in matches]
        assert all(isinstance(sid, str) for sid in ids)
```

**Step 2: Run**

```bash
pytest tests/domain/services/flows/test_plan_act_skill_matching.py -v
```

Expected: PASS (these test the matcher integration, not the full flow)

**Step 3: Modify PlanActFlow._run_with_trace()**

In `plan_act.py`, after `_init_skill_invoke_tool()` (~line 2151), add skill auto-detection:

```python
# Auto-detect skills from user message (Agent UX v2)
settings = get_settings()
if settings.skill_auto_detection_enabled and message.message:
    from app.domain.services.skill_matcher import SkillMatcher

    try:
        registry = get_skill_registry()
        await registry._ensure_fresh()
        all_skills = registry._skills_cache or []
        matcher = SkillMatcher()
        auto_matches = matcher.match(
            message.message,
            all_skills,
            threshold=settings.skill_auto_detection_threshold,
        )
        if auto_matches:
            auto_skill_ids = [m.skill.id for m in auto_matches]
            existing = set(message.skills or [])
            new_ids = [sid for sid in auto_skill_ids if sid not in existing]
            if new_ids:
                message.skills = list(existing | set(new_ids))
                logger.info("Auto-detected skills: %s", [m.skill.name for m in auto_matches if m.skill.id in new_ids])
                # Emit SkillEvents for auto-detected skills
                if settings.skill_ui_events_enabled:
                    from app.domain.models.event import SkillEvent
                    for m in auto_matches:
                        if m.skill.id in new_ids:
                            yield SkillEvent(
                                skill_id=m.skill.id,
                                skill_name=m.skill.name,
                                action="activated",
                                reason=m.reason,
                            )
    except Exception:
        logger.warning("Skill auto-detection failed, continuing without", exc_info=True)
```

**Step 4: Modify execution.py — emit SkillEvent on activation**

In `execute_step()` (line ~339), after injecting skill context:

```python
# Emit SkillEvent for user visibility (Agent UX v2)
settings = get_settings()
if settings.skill_ui_events_enabled and skill_context.prompt_addition:
    from app.domain.models.event import SkillEvent
    for sid in skill_context.skill_ids:
        skill = registry.get_skill(sid)
        if skill:
            yield SkillEvent(
                skill_id=sid,
                skill_name=skill.name,
                action="activated",
                reason=f"Step requires {skill.category.value} capabilities",
                tools_affected=list(skill_context.allowed_tools) if skill_context.allowed_tools else None,
            )
```

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/domain/services/agents/execution.py backend/tests/domain/services/flows/test_plan_act_skill_matching.py
git commit -m "feat(skills): integrate SkillMatcher into PlanActFlow for auto-detection before planning"
```

---

## Task 8: Terminal Mastery Prompt

**Files:**
- Create: `backend/app/domain/services/prompts/terminal_mastery.py`
- Modify: `backend/app/domain/services/prompts/system.py` (add to `TOOL_SECTION_MAP` and `build_system_prompt()`)
- Test: `backend/tests/domain/services/prompts/test_terminal_mastery.py`

**Step 1: Write test**

```python
# backend/tests/domain/services/prompts/test_terminal_mastery.py
from app.domain.services.prompts.terminal_mastery import (
    TERMINAL_MASTERY_RULES,
    TOOL_PREFERENCE_HINTS,
)


def test_terminal_mastery_rules_non_empty():
    assert len(TERMINAL_MASTERY_RULES) > 200
    assert "ripgrep" in TERMINAL_MASTERY_RULES.lower() or "rg" in TERMINAL_MASTERY_RULES
    assert "jq" in TERMINAL_MASTERY_RULES
    assert "curl" in TERMINAL_MASTERY_RULES


def test_tool_preference_hints_non_empty():
    assert len(TOOL_PREFERENCE_HINTS) > 100
    assert "shell_exec" in TOOL_PREFERENCE_HINTS or "terminal" in TOOL_PREFERENCE_HINTS.lower()


def test_terminal_mastery_includes_pipe_guidance():
    assert "pipe" in TERMINAL_MASTERY_RULES.lower() or "|" in TERMINAL_MASTERY_RULES


def test_terminal_mastery_includes_error_handling():
    assert "pipefail" in TERMINAL_MASTERY_RULES or "set -e" in TERMINAL_MASTERY_RULES
```

**Step 2: Run to verify failure**

```bash
pytest tests/domain/services/prompts/test_terminal_mastery.py -v
```

**Step 3: Write implementation**

```python
# backend/app/domain/services/prompts/terminal_mastery.py
"""Terminal mastery prompt sections for Agent UX v2.

Injected into the agent system prompt when shell tools are present
to improve terminal command quality and encourage proactive shell usage.
"""

TERMINAL_MASTERY_RULES = """
## Terminal Mastery

You have a full Linux sandbox with powerful CLI tools. Use them effectively:

### Available Tools
ripgrep (rg), jq, git, gh (GitHub CLI), curl, wget, bc, column, sort, uniq, wc,
head, tail, sed, awk, find, uv (fast Python package manager), pnpm, node, python3.

### Pipe Chains
Chain commands for efficient data processing:
- `curl -s URL | jq '.data[] | {name, value}' | head -20`
- `rg -l "pattern" | head -5 | xargs head -20`
- `find . -name "*.py" -exec wc -l {} + | sort -rn | head -10`
- `git log --oneline -20 | column -t`

### Progress Visibility
Prefer commands that show progress so the user sees activity:
- `uv pip install pandas` (built-in progress bar)
- `curl --progress-bar -O URL` (progress indicator)
- `git clone --progress URL` (transfer progress)

### Structured Output
Format output for readability:
- Use `jq -r '.[] | [.name, .value] | @tsv'` for tab-separated output
- Use `column -t -s','` for aligned columns from CSV
- Use `sort -k2 -rn` for numeric sorting

### Multi-Line Scripts
For scripts longer than one line, use `set -euo pipefail`:
```bash
set -euo pipefail
# Your script here — exits on first error, catches pipe failures
```

### Parallel Execution
Run independent commands concurrently:
```bash
cmd1 & cmd2 & wait  # Run both, wait for all to finish
```
""".strip()

TOOL_PREFERENCE_HINTS = """
## Tool Selection Preferences

Choose the most efficient tool for each task:
- **API data**: Use `curl -s URL | jq` via shell_exec, not browser_navigate
- **Package install**: Use `uv pip install` or `pnpm add` via shell_exec
- **File search**: Use `rg "pattern"` or `find . -name` via shell_exec
- **Git operations**: Use `git` commands via shell_exec
- **Data processing**: Use code_execute_python for complex transformations
- **Web content**: Use browser_navigate only when you need to interact with a page (click, fill forms)
- **Simple downloads**: Use `curl -O` or `wget` via shell_exec, not browser_navigate
""".strip()
```

**Step 4: Integrate into system.py**

In `system.py`, import the new constants and add them to `build_system_prompt()`:

```python
from app.domain.services.prompts.terminal_mastery import (
    TERMINAL_MASTERY_RULES,
    TOOL_PREFERENCE_HINTS,
)
```

In `build_system_prompt()`, add after the `SHELL_RULES` section inclusion:

```python
settings = get_settings()
if include_shell and settings.terminal_mastery_prompt_enabled:
    sections.append(TERMINAL_MASTERY_RULES)
if settings.terminal_proactive_preference_enabled:
    sections.append(TOOL_PREFERENCE_HINTS)
```

**Step 5: Run tests**

```bash
pytest tests/domain/services/prompts/test_terminal_mastery.py -v
```

Expected: PASS (4 tests)

**Step 6: Commit**

```bash
git add backend/app/domain/services/prompts/terminal_mastery.py backend/app/domain/services/prompts/system.py backend/tests/domain/services/prompts/test_terminal_mastery.py
git commit -m "feat(prompts): add terminal mastery rules and tool preference hints for smarter agent shell usage"
```

---

## Task 9: Frontend — TerminalLiveView Component (xterm.js)

**Files:**
- Create: `frontend/src/composables/useTerminalStream.ts`
- Create: `frontend/src/components/toolViews/TerminalLiveView.vue`
- Modify: `frontend/src/components/toolViews/ShellToolView.vue` (delegate to TerminalLiveView when live)

**Step 1: Create useTerminalStream composable**

```typescript
// frontend/src/composables/useTerminalStream.ts
import { ref, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export interface TerminalStreamOptions {
  sessionId: string
  shellSessionId: string
}

/**
 * Composable that consumes ToolStreamEvent SSE events with content_type="terminal"
 * and provides a writable stream of text chunks for xterm.js.
 */
export function useTerminalStream(options: TerminalStreamOptions) {
  const buffer = ref<string[]>([])
  const isComplete = ref(false)
  const exitCode = ref<number | null>(null)

  // Listeners registered externally (by the xterm component)
  type DataListener = (data: string) => void
  const listeners: DataListener[] = []

  function onData(listener: DataListener) {
    listeners.push(listener)
  }

  function pushChunk(text: string) {
    buffer.value.push(text)
    for (const listener of listeners) {
      listener(text)
    }
  }

  function markComplete(code: number) {
    isComplete.value = true
    exitCode.value = code
  }

  function reset() {
    buffer.value = []
    isComplete.value = false
    exitCode.value = null
  }

  onUnmounted(() => {
    listeners.length = 0
  })

  return {
    buffer,
    isComplete,
    exitCode,
    onData,
    pushChunk,
    markComplete,
    reset,
  }
}
```

**Step 2: Create TerminalLiveView component**

```vue
<!-- frontend/src/components/toolViews/TerminalLiveView.vue -->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const props = defineProps<{
  sessionId: string
  shellSessionId: string
  command?: string
}>()

const terminalRef = ref<HTMLDivElement>()
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

function initTerminal() {
  if (!terminalRef.value) return

  terminal = new Terminal({
    theme: {
      background: '#1a1b26',
      foreground: '#c0caf5',
      cursor: '#c0caf5',
      selectionBackground: '#33467c',
      black: '#15161e',
      red: '#f7768e',
      green: '#9ece6a',
      yellow: '#e0af68',
      blue: '#7aa2f7',
      magenta: '#bb9af7',
      cyan: '#7dcfff',
      white: '#a9b1d6',
    },
    fontSize: 13,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    cursorBlink: true,
    cursorStyle: 'bar',
    scrollback: 5000,
    convertEol: true,
    allowProposedApi: true,
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalRef.value)

  nextTick(() => {
    fitAddon?.fit()
  })

  // Auto-resize on container size change
  resizeObserver = new ResizeObserver(() => {
    fitAddon?.fit()
  })
  resizeObserver.observe(terminalRef.value)

  // Show initial command if provided
  if (props.command) {
    terminal.writeln(`\x1b[32m$\x1b[0m ${props.command}`)
  }
}

function writeData(data: string) {
  terminal?.write(data)
}

function writeComplete(exitCode: number) {
  if (terminal) {
    terminal.writeln('')
    if (exitCode === 0) {
      terminal.writeln(`\x1b[32m[Process exited with code ${exitCode}]\x1b[0m`)
    } else {
      terminal.writeln(`\x1b[31m[Process exited with code ${exitCode}]\x1b[0m`)
    }
  }
}

function clear() {
  terminal?.clear()
}

onMounted(() => {
  initTerminal()
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  terminal?.dispose()
  terminal = null
  fitAddon = null
})

defineExpose({
  writeData,
  writeComplete,
  clear,
})
</script>

<template>
  <div class="terminal-live-container">
    <div ref="terminalRef" class="terminal-element" />
  </div>
</template>

<style scoped>
.terminal-live-container {
  width: 100%;
  height: 100%;
  min-height: 120px;
  background: #1a1b26;
  border-radius: 6px;
  overflow: hidden;
}

.terminal-element {
  width: 100%;
  height: 100%;
  padding: 4px;
}
</style>
```

**Step 3: Modify ShellToolView to use TerminalLiveView when live**

In `ShellToolView.vue`, add conditional rendering. When `props.live === true` and the feature is enabled, render `TerminalLiveView` instead of the static Shiki view. Keep the existing Shiki view for completed (non-live) tool results.

Add import and conditional component:

```vue
<script setup>
import TerminalLiveView from './TerminalLiveView.vue'
// ... existing imports
</script>

<template>
  <!-- When live streaming is active, use xterm.js -->
  <TerminalLiveView
    v-if="live && terminalLiveEnabled"
    ref="terminalLiveRef"
    :session-id="sessionId"
    :shell-session-id="shellSessionId"
    :command="currentCommand"
  />
  <!-- Existing static view for completed results -->
  <div v-else class="shell-content">
    <!-- ... existing template ... -->
  </div>
</template>
```

**Step 4: Lint**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 5: Commit**

```bash
git add frontend/src/composables/useTerminalStream.ts frontend/src/components/toolViews/TerminalLiveView.vue frontend/src/components/toolViews/ShellToolView.vue
git commit -m "feat(frontend): add xterm.js TerminalLiveView for real-time terminal streaming"
```

---

## Task 10: Frontend — Skill Events Composable & Activity Bar

**Files:**
- Create: `frontend/src/composables/useSkillEvents.ts`
- Create: `frontend/src/components/AgentActivityBar.vue`

**Step 1: Create useSkillEvents composable**

```typescript
// frontend/src/composables/useSkillEvents.ts
import { ref, computed } from 'vue'

export interface SkillEventData {
  skill_id: string
  skill_name: string
  action: 'activated' | 'deactivated' | 'matched'
  reason: string
  tools_affected?: string[]
  timestamp: string
}

export function useSkillEvents() {
  const activeSkills = ref<Map<string, SkillEventData>>(new Map())
  const recentNotifications = ref<SkillEventData[]>([])

  const activeSkillList = computed(() => Array.from(activeSkills.value.values()))

  function handleSkillEvent(event: SkillEventData) {
    if (event.action === 'activated' || event.action === 'matched') {
      activeSkills.value.set(event.skill_id, event)
      recentNotifications.value.push(event)
      // Auto-remove notification after 4s
      setTimeout(() => {
        const idx = recentNotifications.value.indexOf(event)
        if (idx >= 0) recentNotifications.value.splice(idx, 1)
      }, 4000)
    } else if (event.action === 'deactivated') {
      activeSkills.value.delete(event.skill_id)
    }
  }

  function reset() {
    activeSkills.value.clear()
    recentNotifications.value = []
  }

  return {
    activeSkills,
    activeSkillList,
    recentNotifications,
    handleSkillEvent,
    reset,
  }
}
```

**Step 2: Create AgentActivityBar component**

```vue
<!-- frontend/src/components/AgentActivityBar.vue -->
<script setup lang="ts">
import { computed } from 'vue'
import type { SkillEventData } from '@/composables/useSkillEvents'

const props = defineProps<{
  phase: string
  activeSkills: SkillEventData[]
  currentTool?: string
  currentToolDetail?: string
  stepProgress?: string
  elapsedTime?: string
}>()

const phaseIcon = computed(() => {
  const icons: Record<string, string> = {
    planning: '\u{1F9E0}',
    executing: '\u{26A1}',
    reflecting: '\u{1F914}',
    verifying: '\u{2705}',
  }
  return icons[props.phase?.toLowerCase()] ?? '\u{2699}'
})

const skillColors: Record<string, string> = {
  research: '#7aa2f7',
  coding: '#9ece6a',
  browser: '#e0af68',
  data_analysis: '#bb9af7',
  file_management: '#7dcfff',
  communication: '#f7768e',
  custom: '#a9b1d6',
}

function getSkillColor(skill: SkillEventData): string {
  // Extract category from skill name heuristic
  const name = skill.skill_name.toLowerCase()
  for (const [key, color] of Object.entries(skillColors)) {
    if (name.includes(key.replace('_', ' ')) || name.includes(key.replace('_', ''))) {
      return color
    }
  }
  return skillColors.custom
}
</script>

<template>
  <div class="activity-bar">
    <!-- Phase -->
    <div class="activity-segment phase-segment">
      <span class="phase-icon">{{ phaseIcon }}</span>
      <span class="phase-label">{{ phase }}</span>
    </div>

    <!-- Active Skills -->
    <div v-if="activeSkills.length" class="activity-segment skills-segment">
      <span
        v-for="skill in activeSkills"
        :key="skill.skill_id"
        class="skill-badge"
        :style="{ backgroundColor: getSkillColor(skill) + '22', color: getSkillColor(skill), borderColor: getSkillColor(skill) + '44' }"
        :title="skill.reason"
      >
        {{ skill.skill_name }}
      </span>
    </div>

    <!-- Current Tool -->
    <div v-if="currentTool" class="activity-segment tool-segment">
      <span class="tool-spinner" />
      <span class="tool-name">{{ currentTool }}</span>
      <span v-if="currentToolDetail" class="tool-detail">{{ currentToolDetail }}</span>
    </div>

    <!-- Step Progress -->
    <div v-if="stepProgress" class="activity-segment progress-segment">
      <span class="step-progress">{{ stepProgress }}</span>
      <span v-if="elapsedTime" class="elapsed-time">{{ elapsedTime }}</span>
    </div>
  </div>
</template>

<style scoped>
.activity-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  background: var(--bg-secondary, #1e1f2e);
  border-bottom: 1px solid var(--border-color, #2a2b3d);
  font-size: 12px;
  min-height: 32px;
  overflow-x: auto;
}

.activity-segment {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.phase-segment {
  font-weight: 600;
  color: var(--text-primary, #c0caf5);
}

.phase-icon {
  font-size: 14px;
}

.phase-label {
  text-transform: capitalize;
}

.skill-badge {
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid;
  font-size: 11px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.tool-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--text-secondary, #565f89);
  border-top-color: var(--accent, #7aa2f7);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.tool-name {
  color: var(--accent, #7aa2f7);
  font-weight: 500;
}

.tool-detail {
  color: var(--text-secondary, #565f89);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-segment {
  margin-left: auto;
  color: var(--text-secondary, #565f89);
}

.step-progress {
  font-weight: 500;
}

.elapsed-time {
  opacity: 0.7;
}
</style>
```

**Step 3: Lint**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 4: Commit**

```bash
git add frontend/src/composables/useSkillEvents.ts frontend/src/components/AgentActivityBar.vue
git commit -m "feat(frontend): add AgentActivityBar and useSkillEvents for skill-driven UI feedback"
```

---

## Task 11: Frontend — Browser Interaction Overlay

**Files:**
- Create: `frontend/src/components/BrowserInteractionOverlay.vue`

**Step 1: Create overlay component**

```vue
<!-- frontend/src/components/BrowserInteractionOverlay.vue -->
<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  lastAction?: {
    type: 'navigate' | 'click' | 'scroll_up' | 'scroll_down' | 'type'
    url?: string
    x?: number
    y?: number
    text?: string
  }
  containerWidth: number
  containerHeight: number
  scaleX: number
  scaleY: number
}>()

const navToast = ref<{ url: string; visible: boolean }>({ url: '', visible: false })
const clickRipple = ref<{ x: number; y: number; visible: boolean }>({ x: 0, y: 0, visible: false })
const scrollIndicator = ref<{ direction: 'up' | 'down'; visible: boolean }>({ direction: 'down', visible: false })

let navTimeout: ReturnType<typeof setTimeout> | null = null
let rippleTimeout: ReturnType<typeof setTimeout> | null = null
let scrollTimeout: ReturnType<typeof setTimeout> | null = null

watch(() => props.lastAction, (action) => {
  if (!action) return

  if (action.type === 'navigate' && action.url) {
    navToast.value = { url: action.url, visible: true }
    if (navTimeout) clearTimeout(navTimeout)
    navTimeout = setTimeout(() => {
      navToast.value.visible = false
    }, 2500)
  }

  if (action.type === 'click' && action.x != null && action.y != null) {
    clickRipple.value = {
      x: action.x * props.scaleX,
      y: action.y * props.scaleY,
      visible: true,
    }
    if (rippleTimeout) clearTimeout(rippleTimeout)
    rippleTimeout = setTimeout(() => {
      clickRipple.value.visible = false
    }, 600)
  }

  if (action.type === 'scroll_up' || action.type === 'scroll_down') {
    scrollIndicator.value = {
      direction: action.type === 'scroll_up' ? 'up' : 'down',
      visible: true,
    }
    if (scrollTimeout) clearTimeout(scrollTimeout)
    scrollTimeout = setTimeout(() => {
      scrollIndicator.value.visible = false
    }, 800)
  }
}, { deep: true })
</script>

<template>
  <div class="interaction-overlay">
    <!-- Navigation Toast -->
    <Transition name="nav-toast">
      <div v-if="navToast.visible" class="nav-toast">
        <span class="nav-icon">&#x1F310;</span>
        <span class="nav-url">{{ navToast.url }}</span>
      </div>
    </Transition>

    <!-- Click Ripple -->
    <Transition name="ripple">
      <div
        v-if="clickRipple.visible"
        class="click-ripple"
        :style="{ left: clickRipple.x + 'px', top: clickRipple.y + 'px' }"
      />
    </Transition>

    <!-- Scroll Indicator -->
    <Transition name="scroll-ind">
      <div
        v-if="scrollIndicator.visible"
        class="scroll-indicator"
        :class="scrollIndicator.direction"
      >
        <span v-if="scrollIndicator.direction === 'up'">&#x25B2;</span>
        <span v-else>&#x25BC;</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.interaction-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
  overflow: hidden;
}

/* Navigation Toast */
.nav-toast {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 14px;
  background: rgba(26, 27, 38, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 16px;
  border: 1px solid rgba(122, 162, 247, 0.3);
  color: #c0caf5;
  font-size: 11px;
  max-width: 80%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-icon {
  font-size: 12px;
}

.nav-url {
  opacity: 0.9;
}

.nav-toast-enter-active { transition: all 0.3s ease-out; }
.nav-toast-leave-active { transition: all 0.4s ease-in; }
.nav-toast-enter-from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
.nav-toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-5px); }

/* Click Ripple */
.click-ripple {
  position: absolute;
  width: 30px;
  height: 30px;
  margin-left: -15px;
  margin-top: -15px;
  border-radius: 50%;
  background: rgba(122, 162, 247, 0.3);
  animation: ripple-expand 0.5s ease-out forwards;
}

@keyframes ripple-expand {
  0% { transform: scale(0.3); opacity: 1; }
  100% { transform: scale(2.5); opacity: 0; }
}

.ripple-enter-active { animation: ripple-expand 0.5s ease-out; }
.ripple-leave-active { transition: opacity 0.1s; }
.ripple-leave-to { opacity: 0; }

/* Scroll Indicator */
.scroll-indicator {
  position: absolute;
  right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(26, 27, 38, 0.7);
  backdrop-filter: blur(4px);
  color: #7aa2f7;
  font-size: 14px;
}

.scroll-indicator.up { top: 40px; }
.scroll-indicator.down { bottom: 40px; }

.scroll-ind-enter-active { transition: all 0.2s ease-out; }
.scroll-ind-leave-active { transition: all 0.3s ease-in; }
.scroll-ind-enter-from { opacity: 0; transform: scale(0.5); }
.scroll-ind-leave-to { opacity: 0; }
</style>
```

**Step 2: Lint**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 3: Commit**

```bash
git add frontend/src/components/BrowserInteractionOverlay.vue
git commit -m "feat(frontend): add BrowserInteractionOverlay with nav toast, click ripple, scroll indicators"
```

---

## Task 12: Integration — Wire Components into Chat Layout

**Files:**
- Modify: `frontend/src/components/SandboxViewer.vue` (add overlay + activity bar)
- Modify: Parent chat page component that hosts `SandboxViewer` (add split-view terminal)

**Step 1: Add BrowserInteractionOverlay to SandboxViewer**

In `SandboxViewer.vue`, import and render `BrowserInteractionOverlay` as a sibling to `KonvaLiveStage` inside a `position: relative` wrapper:

```vue
<script setup>
import BrowserInteractionOverlay from './BrowserInteractionOverlay.vue'
import AgentActivityBar from './AgentActivityBar.vue'
</script>

<template>
  <div class="sandbox-viewer-container">
    <AgentActivityBar
      :phase="currentPhase"
      :active-skills="activeSkills"
      :current-tool="currentToolName"
      :current-tool-detail="currentToolDetail"
      :step-progress="stepProgress"
    />
    <div class="viewer-body" style="position: relative;">
      <KonvaLiveStage ref="liveStageRef" ... />
      <BrowserInteractionOverlay
        :last-action="lastBrowserAction"
        :container-width="containerWidth"
        :container-height="containerHeight"
        :scale-x="scaleX"
        :scale-y="scaleY"
      />
    </div>
  </div>
</template>
```

**Step 2: Wire SSE events to activity bar and overlay**

In the SSE event handler (where tool events are processed), route:
- `SkillEvent` → `useSkillEvents().handleSkillEvent()`
- `ToolEvent` with browser actions → update `lastBrowserAction` ref for overlay
- `FlowTransitionEvent` → update `currentPhase`

**Step 3: Lint and type-check**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 4: Commit**

```bash
git add frontend/src/components/SandboxViewer.vue
git commit -m "feat(frontend): wire AgentActivityBar and BrowserInteractionOverlay into SandboxViewer"
```

---

## Task 13: Full Integration Test & Linting

**Files:**
- All modified files

**Step 1: Run backend tests**

```bash
cd backend && conda activate pythinker
pytest tests/ -x -q --timeout=60
```

Expected: All existing tests pass, plus ~30 new tests from tasks 1-8.

**Step 2: Run backend linting**

```bash
ruff check . && ruff format --check .
```

**Step 3: Run frontend checks**

```bash
cd frontend && bun run lint && bun run type-check
```

**Step 4: Fix any issues found**

Address lint errors, type errors, or test failures.

**Step 5: Final commit (if fixes needed)**

```bash
git add -u
git commit -m "fix(ux-v2): address lint and test issues from integration"
```

---

## Task 14: Rebuild & Manual Verification

**Step 1: Rebuild sandbox**

```bash
docker compose build --no-cache sandbox
```

**Step 2: Start full stack**

```bash
./dev.sh watch
```

**Step 3: Verify browser choreography**

- Open a session and ask the agent to research something
- Verify: Chrome address bar visible in screencast
- Verify: 5-7 second dwell on pages before extraction
- Verify: Smooth cursor movement to click targets
- Verify: Realistic typing speed (~65ms/char)

**Step 4: Verify terminal enhancement**

- Ask agent to install a package via terminal
- Verify: xterm.js live rendering (not 5s polling)
- Verify: ANSI colors render properly
- Verify: Auto-scroll works

**Step 5: Verify skill system**

- Ask a research question
- Verify: SkillEvent appears in AgentActivityBar
- Verify: Skill badge shows "Research" or similar
- Verify: Tool indicator shows current tool

**Step 6: Verify interaction overlay**

- Watch browser navigation — URL toast appears briefly
- Watch clicks — ripple animation at click coordinates
- Watch scrolls — directional indicator appears

---

## Summary: Commit Sequence

| # | Scope | Message |
|---|---|---|
| 1 | config | `feat(config): add Agent UX v2 feature flags for choreography, terminal, skills` |
| 2 | browser | `feat(browser): add BrowserChoreographer with fast/professional/cinematic timing profiles` |
| 3 | browser | `feat(browser): inject BrowserChoreographer into PlaywrightBrowser actions` |
| 4 | screencast | `feat(screencast): include Chrome UI (address bar) in CDP screencast frames` |
| 5 | events | `feat(events): add SkillEvent for user-visible skill activation feedback` |
| 6 | skills | `feat(skills): add SkillMatcher for auto-detection from user messages` |
| 7 | skills | `feat(skills): integrate SkillMatcher into PlanActFlow for auto-detection before planning` |
| 8 | prompts | `feat(prompts): add terminal mastery rules and tool preference hints` |
| 9 | frontend | `feat(frontend): add xterm.js TerminalLiveView for real-time terminal streaming` |
| 10 | frontend | `feat(frontend): add AgentActivityBar and useSkillEvents for skill-driven UI feedback` |
| 11 | frontend | `feat(frontend): add BrowserInteractionOverlay with nav toast, click ripple, scroll indicators` |
| 12 | frontend | `feat(frontend): wire AgentActivityBar and BrowserInteractionOverlay into SandboxViewer` |
| 13 | fix | `fix(ux-v2): address lint and test issues from integration` |
| 14 | — | Manual verification (no commit) |
