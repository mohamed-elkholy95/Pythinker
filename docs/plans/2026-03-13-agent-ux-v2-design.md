# Agent UX v2 — Professional Browser Choreography, Terminal Enhancement & Skill-Driven Architecture

**Date:** 2026-03-13
**Status:** Design Approved
**Scope:** Single unified release — all four feature areas shipped together

---

## Problem Statement

The current agent UX has four key gaps:

1. **Browser interactions feel robotic** — No dwell time on pages (content is extracted immediately after navigation), minimal cursor animation (0.1s), typing at 10ms/char. The CDP screencast crops Chrome's address bar, so users can't see what URL the agent is visiting.
2. **Terminal is underutilized and poorly displayed** — Frontend polls every 5s with static Shiki-highlighted HTML. Agents use basic commands and over-rely on browser tools when shell commands would be faster.
3. **Skills are implemented but dormant** — Full skill system exists (model, registry, invoke tool) but agents don't proactively detect or load skills. Users never see skill activation.
4. **No professional activity feedback** — Users can't tell what the agent is doing, which skill governs behavior, or why certain tools are chosen.

---

## Design Decisions

### Approach: Backend-Driven Choreography

All interaction timing, cursor animation, and skill orchestration lives in the **backend**. The frontend is a consumer of structured events and JPEG frames — it doesn't own choreography logic.

**Rationale:**
- Address bar visibility requires sandbox-level changes (can't be done in frontend)
- Cursor movement must happen in real Chrome to appear in CDP screencast frames
- Model-agnostic — any LLM benefits from human-like pacing without prompt changes
- Single source of truth for interaction behavior

---

## Section 1: Browser Visual Choreography

### 1.1 Show Chrome UI in Screencast

**Current state:**
- `ScreencastConfig(max_height=900)` at `sandbox/app/services/cdp_screencast.py:67`
- `_ensure_viewport()` forces `Emulation.setDeviceMetricsOverride(height=900)` at lines 467-482
- `Page.startScreencast(maxHeight=900)` captures viewport only — Chrome UI cropped
- Frontend `forceDimensionReset(1280, 900)` hardcoded in `SandboxViewer.vue:230`

**Changes:**
- `ScreencastConfig.max_height` → 1024 (matches Xvfb screen)
- Remove/adjust `_ensure_viewport()` to not override device metrics (let Chrome render naturally)
- `SandboxViewer.vue` → `forceDimensionReset(1280, 1024)`
- `frontend/src/types/liveViewer.ts` → `SANDBOX_HEIGHT = 1024`
- Add `SCREENCAST_INCLUDE_CHROME_UI` setting to `sandbox/app/core/config.py`

**Result:** Screencast frames include Chrome's address bar, tab strip, loading indicator, HTTPS lock icon — all real browser UI.

### 1.2 Interaction Choreography Engine

New file: `backend/app/infrastructure/external/browser/choreography.py`

```python
@dataclass
class ChoreographyProfile:
    """Timing profile for browser interactions."""
    name: str
    dwell_after_navigate: float      # seconds to pause after page load
    hover_before_click: float        # hover pause before clicking
    cursor_move_steps: int           # Playwright mouse.move() subdivisions
    cursor_move_duration: float      # total cursor travel time
    typing_delay_ms: int             # per-character delay
    scroll_step_pause: float         # between scroll increments
    post_click_settle: float         # after click, let page react
    post_type_pause: float           # after finishing typing
    pre_action_pause: float          # brief pause before any action

PROFILES = {
    "fast": ChoreographyProfile(
        name="fast",
        dwell_after_navigate=1.0, hover_before_click=0.1,
        cursor_move_steps=5, cursor_move_duration=0.15,
        typing_delay_ms=10, scroll_step_pause=0.3,
        post_click_settle=0.3, post_type_pause=0.1,
        pre_action_pause=0.05,
    ),
    "professional": ChoreographyProfile(
        name="professional",
        dwell_after_navigate=7.0, hover_before_click=0.4,
        cursor_move_steps=20, cursor_move_duration=0.6,
        typing_delay_ms=65, scroll_step_pause=0.8,
        post_click_settle=1.5, post_type_pause=0.5,
        pre_action_pause=0.3,
    ),
    "cinematic": ChoreographyProfile(
        name="cinematic",
        dwell_after_navigate=10.0, hover_before_click=0.8,
        cursor_move_steps=40, cursor_move_duration=1.2,
        typing_delay_ms=100, scroll_step_pause=1.2,
        post_click_settle=2.5, post_type_pause=1.0,
        pre_action_pause=0.5,
    ),
}
```

`BrowserChoreographer` wraps `PlaywrightBrowser` methods:

**Navigate flow:**
1. `page.goto(url, wait_until='domcontentloaded')` — standard
2. `asyncio.sleep(profile.dwell_after_navigate)` — **5-10s dwell** — user sees the page
3. Content extraction proceeds

**Click flow:**
1. `asyncio.sleep(profile.pre_action_pause)` — brief pre-action pause
2. `page.mouse.move(target_x, target_y, steps=profile.cursor_move_steps)` — smooth cursor travel visible in screencast
3. `asyncio.sleep(profile.hover_before_click)` — visible hover state
4. `page.mouse.click(target_x, target_y)` — the click
5. `asyncio.sleep(profile.post_click_settle)` — let page react

**Type flow:**
1. Focus element
2. `page.keyboard.type(text, delay=profile.typing_delay_ms)` — 65ms/char (human ~60-80ms)
3. `asyncio.sleep(profile.post_type_pause)` — pause after typing

**Scroll flow:**
1. `page.mouse.wheel(0, delta)` — native wheel event
2. `asyncio.sleep(profile.scroll_step_pause)` — visible pause between increments

### 1.3 Feature Flags

```python
# backend/app/core/config.py
browser_choreography_enabled: bool = True
browser_choreography_profile: str = "professional"
browser_screencast_include_chrome_ui: bool = True
```

---

## Section 2: Terminal Enhancement

### 2.1 Live Terminal Emulator (xterm.js)

**Current:** `ShellToolView.vue` polls every 5s, renders static HTML with Shiki.

**New:** `TerminalLiveView.vue` using `@xterm/xterm` + `@xterm/addon-fit` + `@xterm/addon-webgl`.

- Consumes `ToolStreamEvent(content_type="terminal")` from the SSE event bus
- Characters render incrementally as they arrive — real terminal feel
- Full ANSI color/escape sequence support (xterm.js handles natively)
- Auto-scroll with smart pause (stops auto-scroll when user scrolls up)
- Copy support via xterm.js selection
- Falls back to current Shiki view for completed/historical commands

**Composable:** `useTerminalStream.ts`
- Subscribes to agent SSE events filtered by `content_type === "terminal"`
- Buffers incoming text and writes to xterm.js instance
- Handles session lifecycle (new session → clear terminal, session end → freeze)

### 2.2 Agent Terminal Intelligence

New prompt section: `backend/app/domain/services/prompts/terminal_mastery.py`

Injected into system prompt when `AgentCapability.SHELL_COMMANDS` is present:

**Key prompt content:**
- **Pipe chains:** "Prefer `curl -s URL | jq '.data[]' | head -20` over browser_navigate for API data"
- **Installed tools:** Explicit list of available sandbox tools (ripgrep, jq, git, gh, uv, pnpm, bc, curl, wget, column)
- **Progress visibility:** "Use commands that show progress: `uv pip install` (progress bar built-in), `curl --progress-bar`"
- **Structured output:** "Use `column -t`, `jq -r`, `sort -k2 -rn` for human-readable terminal output"
- **Error handling:** "Use `set -euo pipefail` for multi-line scripts"
- **Parallel execution:** "Use `cmd1 & cmd2 & wait` for independent operations"

### 2.3 Tool Preference Guidance

Added to `StepContextAssembler` as `TOOL_PREFERENCE_HINTS`:

| Task pattern | Preferred tool | Instead of |
|---|---|---|
| Fetch API data | `curl` + `jq` via `shell_exec` | `browser_navigate` |
| Install packages | `uv pip install` / `pnpm add` | Browser search for instructions |
| Search files | `rg` / `find` via `shell_exec` | Repeated `file_read` |
| Git operations | `git` commands | `file_read` + `file_write` |
| Data processing | `code_execute_python` | Manual multi-step file operations |

### 2.4 Split-View Terminal in Sandbox Panel

`SandboxViewer.vue` gets a split-view mode:
- **Top:** Browser screencast (KonvaLiveStage) — resizable via drag handle
- **Bottom:** Live terminal (TerminalLiveView) — shows active shell session
- Toggle modes: full-browser / full-terminal / split (default: split)
- Activity indicator on each tab when new content arrives in the hidden panel

---

## Section 3: Skill-Driven Agent Architecture

### 3.1 Skill Auto-Detection

New service: `backend/app/domain/services/skill_matcher.py`

```python
class SkillMatcher:
    """Matches user messages to relevant skills."""

    async def match(
        self,
        message: str,
        available_skills: list[Skill],
        threshold: float = 0.6,
    ) -> list[SkillMatch]:
        """Return skills matching the message, ranked by confidence."""
        matches = []
        for skill in available_skills:
            score = self._compute_match_score(message, skill)
            if score >= threshold:
                matches.append(SkillMatch(skill=skill, confidence=score, reason=reason))
        return sorted(matches, key=lambda m: m.confidence, reverse=True)

    def _compute_match_score(self, message: str, skill: Skill) -> float:
        """Score based on trigger_patterns (regex) + keyword overlap."""
        # 1. Regex trigger patterns (highest signal)
        # 2. Required tools vs task keywords
        # 3. Category keyword matching
```

**Integration point:** `PlanActFlow.run()` calls `SkillMatcher.match()` before `planner.create_plan()`:

```python
# In PlanActFlow.run()
matcher = SkillMatcher()
skill_matches = await matcher.match(message.content, registry.get_all_skills())
auto_skills = [m.skill.id for m in skill_matches]
message.skills = list(set((message.skills or []) + auto_skills))
# Emit SkillEvent for each auto-activated skill
for match in skill_matches:
    yield SkillEvent(action="activated", skill_name=match.skill.name, reason=match.reason)
```

### 3.2 Skill-First Planning

In `PlannerAgent.create_plan()`, skill context is injected into the planning prompt:

1. Active skills' `system_prompt_addition` summaries are appended
2. Plan output schema gets optional `skill_id` per step
3. During execution, each step's `skill_id` auto-activates that skill
4. The existing `execute_step()` skill injection (execution.py:316-367) handles the rest

### 3.3 Skill Events (User-Visible)

New event: `backend/app/domain/events/skill_event.py`

```python
class SkillEvent(BaseEvent):
    event_type: Literal["skill"] = "skill"
    skill_id: str
    skill_name: str
    action: Literal["activated", "deactivated", "matched"]
    reason: str  # "Detected research task patterns", "Step requires browser automation"
    tools_affected: list[str] | None = None  # which tools were enabled/restricted
```

Frontend composable `useSkillEvents.ts` consumes these and feeds `AgentActivityBar.vue`.

### 3.4 Skill-Driven Tool Filtering

Built-in skills should define strict `allowed_tools`:

| Skill | Allowed tools |
|---|---|
| Research | `search`, `browser_navigate`, `browser_view`, `browser_click`, `file_write`, `shell_exec` |
| Coding | `shell_exec`, `code_execute`, `code_execute_python`, `file_read`, `file_write`, `file_str_replace` |
| Browser Automation | All `browser_*` tools + `shell_exec` + `file_write` |
| Data Analysis | `code_execute_python`, `file_read`, `file_write`, `shell_exec`, `browser_navigate` |
| File Management | `file_*` tools + `shell_exec` |

This reduces tool list from 30+ to 5-10 per step, improving LLM tool selection accuracy.

---

## Section 4: Professional UI Feedback

### 4.1 Agent Activity Bar

New component: `AgentActivityBar.vue`

Persistent bar above the sandbox viewer:
- **Phase indicator:** Current phase with icon (Planning/Executing/Reflecting/Verifying)
- **Skill badges:** Active skills shown as colored pills (e.g., "Research", "Coding")
- **Tool indicator:** Current tool in use with spinner (e.g., "Browsing: google.com", "Terminal: pip install pandas")
- **Step progress:** "Step 2/5" with elapsed time

### 4.2 Browser Interaction Overlay

New component: `BrowserInteractionOverlay.vue`

Transparent overlay div positioned above KonvaLiveStage:
- **Navigation toast:** URL appears briefly at top of canvas on navigation, fades after 2s
- **Click ripple:** Material Design ripple animation at click coordinates
- **Scroll indicator:** Small directional arrow during scrolls
- All triggered by `ToolEvent` data (coordinates, URL, action type)

### 4.3 Skill Activation Notification

When a skill is activated:
- Brief slide-in notification from the right edge
- Shows skill icon + name + affected tools
- Auto-dismisses after 3s
- Stacks vertically if multiple skills activate simultaneously

### 4.4 Terminal Integration in Sandbox Panel

Split-view layout in the sandbox viewer panel:
- Drag handle between browser and terminal
- Tab indicators with activity dots
- Full-screen toggle for either panel
- Default split ratio: 65% browser / 35% terminal

---

## Section 5: Configuration

All new settings in `backend/app/core/config.py`:

```python
# Browser Choreography
browser_choreography_enabled: bool = True
browser_choreography_profile: str = "professional"  # fast/professional/cinematic
browser_screencast_include_chrome_ui: bool = True

# Terminal Enhancement
terminal_live_streaming_enabled: bool = True
terminal_mastery_prompt_enabled: bool = True
terminal_proactive_preference_enabled: bool = True

# Skill-Driven Architecture
skill_auto_detection_enabled: bool = True
skill_auto_detection_threshold: float = 0.6
skill_first_planning_enabled: bool = True
skill_ui_events_enabled: bool = True
```

Sandbox settings in `sandbox/app/core/config.py`:

```python
SCREENCAST_INCLUDE_CHROME_UI: bool = True
SCREENCAST_MAX_HEIGHT: int = 1024  # 1024 includes Chrome UI, 900 viewport-only
```

---

## Section 6: Files Changed/Created

### New Files (10)

| File | Purpose |
|---|---|
| `backend/app/infrastructure/external/browser/choreography.py` | `BrowserChoreographer` — timing profiles, cursor movement, dwell |
| `backend/app/domain/services/skill_matcher.py` | `SkillMatcher` — auto-detect skills from user message |
| `backend/app/domain/events/skill_event.py` | `SkillEvent` SSE event type |
| `backend/app/domain/services/prompts/terminal_mastery.py` | Enhanced terminal prompt sections |
| `frontend/src/components/toolViews/TerminalLiveView.vue` | xterm.js live terminal emulator |
| `frontend/src/components/AgentActivityBar.vue` | Persistent activity indicator bar |
| `frontend/src/components/BrowserInteractionOverlay.vue` | Click ripple, nav toast, scroll indicators |
| `frontend/src/composables/useTerminalStream.ts` | Composable consuming terminal SSE events |
| `frontend/src/composables/useSkillEvents.ts` | Composable consuming skill SSE events |
| `docs/plans/2026-03-13-agent-ux-v2-design.md` | This design document |

### Modified Files (14)

| File | Change |
|---|---|
| `sandbox/app/services/cdp_screencast.py` | `ScreencastConfig.max_height` 900→1024, adjust `_ensure_viewport` |
| `sandbox/app/api/v1/screencast.py` | Thread `max_height` param to `ScreencastConfig` |
| `sandbox/app/core/config.py` | Add `SCREENCAST_INCLUDE_CHROME_UI`, `SCREENCAST_MAX_HEIGHT` |
| `backend/app/infrastructure/external/browser/playwright_browser.py` | Inject `BrowserChoreographer`, wrap navigate/click/type/scroll |
| `backend/app/domain/services/flows/plan_act.py` | Call `SkillMatcher` before planning, inject skill context |
| `backend/app/domain/services/agents/execution.py` | Emit `SkillEvent` on skill activation/deactivation |
| `backend/app/domain/services/agents/base.py` | Yield `SkillEvent` in execute loop |
| `backend/app/domain/services/prompts/system.py` | Add `TERMINAL_MASTERY` and `TOOL_PREFERENCE_HINTS` sections |
| `backend/app/core/config.py` | Add all new feature flags (12 settings) |
| `frontend/src/components/SandboxViewer.vue` | `forceDimensionReset(1280, 1024)`, split-view layout |
| `frontend/src/components/KonvaLiveStage.vue` | Support overlay layer for interaction indicators |
| `frontend/src/components/toolViews/ShellToolView.vue` | Delegate to `TerminalLiveView` when live streaming |
| `frontend/src/types/liveViewer.ts` | `SANDBOX_HEIGHT` 900→1024 |
| `frontend/src/composables/useKonvaScreencast.ts` | Handle 1024px height frames |

---

## Architecture Flow (End-to-End)

```
User sends message
  │
  ▼
PlanActFlow.run()
  ├── SkillMatcher.match(message) → [research_skill, coding_skill]
  ├── yield SkillEvent("activated", "Research Skill", reason="Detected research patterns")
  ├── PlannerAgent.create_plan(message + skill_context)
  │     └── Plan steps include skill_id per step
  └── for step in plan:
        ├── ExecutionAgent.execute_step(step)
        │     ├── Activate step.skill_id → filter tools to 5-10, inject prompt
        │     ├── yield SkillEvent("activated", step.skill_name)
        │     └── BaseAgent.execute(prompt)
        │           └── while tool_calls:
        │                 ├── browser_navigate("https://...")
        │                 │     └── BrowserChoreographer:
        │                 │           page.goto() → dwell 7s → extract
        │                 │           (screencast shows Chrome UI + address bar)
        │                 ├── browser_click(element)
        │                 │     └── BrowserChoreographer:
        │                 │           mouse.move(steps=20) → hover 0.4s → click → settle 1.5s
        │                 ├── shell_exec("curl -s api | jq '.data'")
        │                 │     └── ShellOutputPoller → ToolStreamEvent → TerminalLiveView (xterm.js)
        │                 └── code_execute_python(script)
        │                       └── Live output in terminal panel
        └── yield SkillEvent("deactivated", step.skill_name)

Frontend receives:
  ├── JPEG frames (1280x1024, includes Chrome UI with address bar)
  ├── ToolStreamEvent(terminal) → xterm.js live rendering
  ├── SkillEvent → AgentActivityBar badges + skill notification
  └── ToolEvent → AgentActivityBar tool indicator + BrowserInteractionOverlay
```
