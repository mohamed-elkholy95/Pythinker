# Phase 1: Security & Critical Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all critical and high-severity security vulnerabilities across the sandbox, frontend XSS vectors, and authentication layer.

**Architecture:** Security fixes are organized into three independent tracks — sandbox hardening (SEC-001 to SEC-009), XSS prevention (SEC-010 to SEC-013), and auth/authz (SEC-014 to SEC-017). Each track can be worked in parallel. Every fix is independently revertable.

**Tech Stack:** Python 3.12 (FastAPI, asyncio, shlex, secrets), Vue 3 + TypeScript (DOMPurify, marked), Docker (capabilities, seccomp)

**Reference:** `docs/ROADMAP.md` Phase 1

---

## File Structure

### Sandbox Track (backend + sandbox)

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/domain/models/sandbox_security_policy.py` | Remove SYS_CHROOT from allowlist + validator |
| Modify | `backend/app/core/sandbox_manager.py:350` | Remove SYS_CHROOT from cap_add |
| Modify | `sandbox/app/services/file.py:144,223,246,438` | Use shlex.quote on all sudo path interpolations |
| Modify | `sandbox/app/core/config.py:25` | Add startup validation for SANDBOX_API_SECRET |
| Modify | `sandbox/app/core/middleware.py` | Enforce secret in production |
| Modify | `sandbox/app/main.py:58` | Restrict CORS origins |
| Create | `sandbox/tests/test_file_path_injection.py` | Path injection test suite |
| Create | `sandbox/tests/test_auth_enforcement.py` | Auth enforcement tests |
| Create | `backend/tests/domain/models/test_sandbox_security_policy.py` | Policy model tests |

### XSS Track (frontend)

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `frontend/src/utils/sanitize.ts` | Central DOMPurify wrapper |
| Modify | `frontend/src/components/report/FinalSummaryCard.vue:3` | Add DOMPurify sanitization |
| Modify | `frontend/src/components/skill/SkillFilePreview.vue:35` | Add DOMPurify to marked output |
| Modify | `frontend/src/pages/SharePage.vue:107` | Replace v-html with safe interpolation |
| Create | `frontend/src/__tests__/utils/sanitize.test.ts` | Sanitization unit tests |

### Auth Track (backend)

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/interfaces/api/session_routes.py:549` | Add ownership check to cancel |
| Modify | `backend/app/core/config.py` (Settings class) | Add startup validator for jwt_secret_key |
| Modify | `backend/app/interfaces/api/sandbox_callback_routes.py:52` | Use secrets.compare_digest |
| Modify | `backend/app/interfaces/api/auth_routes.py:232,249` | Use UserRole.ADMIN enum |
| Create | `backend/tests/interfaces/api/test_session_cancel_authz.py` | Cancel ownership tests |
| Create | `backend/tests/core/test_config_auth_validation.py` | JWT secret validation tests |

---

## Task 1: Remove SYS_CHROOT Capability (SEC-001)

**Files:**
- Modify: `backend/app/domain/models/sandbox_security_policy.py:17,46`
- Modify: `backend/app/core/sandbox_manager.py:350`
- Create: `backend/tests/domain/models/test_sandbox_security_policy.py`

- [ ] **Step 1: Write the failing test for policy without SYS_CHROOT**

```python
# backend/tests/domain/models/test_sandbox_security_policy.py
import pytest
from app.domain.models.sandbox_security_policy import SandboxSecurityPolicy


class TestSandboxSecurityPolicy:
    def test_default_caps_exclude_sys_chroot(self):
        """SYS_CHROOT must NOT be in the default capability allowlist."""
        policy = SandboxSecurityPolicy()
        assert "SYS_CHROOT" not in policy.cap_add_allowlist

    def test_sys_chroot_rejected_by_validator(self):
        """Attempting to add SYS_CHROOT must raise ValidationError."""
        with pytest.raises(ValueError, match="not in allowlist"):
            SandboxSecurityPolicy(
                cap_add_allowlist=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]
            )

    def test_valid_caps_accepted(self):
        """All valid capabilities without SYS_CHROOT must pass."""
        policy = SandboxSecurityPolicy(
            cap_add_allowlist=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"]
        )
        assert len(policy.cap_add_allowlist) == 4

    def test_cap_drop_must_include_all(self):
        """cap_drop must contain ALL."""
        with pytest.raises(ValueError, match="must include ALL"):
            SandboxSecurityPolicy(cap_drop=["NET_RAW"])

    def test_empty_cap_drop_rejected(self):
        """Empty cap_drop must be rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            SandboxSecurityPolicy(cap_drop=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && conda activate pythinker && pytest tests/domain/models/test_sandbox_security_policy.py -v -p no:cov -o addopts=`
Expected: `test_default_caps_exclude_sys_chroot` FAILS (SYS_CHROOT currently in defaults), `test_sys_chroot_rejected_by_validator` FAILS (currently allowed)

- [ ] **Step 3: Remove SYS_CHROOT from policy model**

In `backend/app/domain/models/sandbox_security_policy.py`:

```python
# Line 17: Remove SYS_CHROOT from default allowlist
cap_add_allowlist: list[str] = ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"]

# Line 46: Remove SYS_CHROOT from validator allowed set
allowed = {"CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"}
```

- [ ] **Step 4: Remove SYS_CHROOT from sandbox_manager.py**

In `backend/app/core/sandbox_manager.py:350`:

```python
# Change:
"cap_add": ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"],
# To:
"cap_add": ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"],
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest tests/domain/models/test_sandbox_security_policy.py -v -p no:cov -o addopts=`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add backend/app/domain/models/sandbox_security_policy.py backend/app/core/sandbox_manager.py backend/tests/domain/models/test_sandbox_security_policy.py
git commit -m "fix(security): remove SYS_CHROOT capability from sandbox containers

SYS_CHROOT enables chroot(2) syscalls — a known container escape
primitive not required by any sandbox workload. Removes from default
allowlist, validator, and EnhancedSandboxManager config.

Ref: SEC-001"
```

---

## Task 2: Fix Path Injection in Sudo File Operations (SEC-003)

**Files:**
- Modify: `sandbox/app/services/file.py:144,223,246,438`
- Create: `sandbox/tests/test_file_path_injection.py`

- [ ] **Step 1: Write the failing test that exercises FileService**

```python
# sandbox/tests/test_file_path_injection.py
import pytest
import shlex
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


class TestPathInjection:
    """Verify that FileService uses shlex.quote on all sudo shell commands."""

    DANGEROUS_FILENAMES = [
        "file'; rm -rf /; echo '",
        'file"; rm -rf /; echo "',
        "file$(whoami)",
        "file`whoami`",
        "file with spaces",
        "file'with'quotes",
    ]

    @pytest.mark.parametrize("filename", DANGEROUS_FILENAMES)
    @pytest.mark.asyncio
    async def test_sudo_read_quotes_filename(self, filename: str):
        """sudo cat command must use shlex.quote on the filename."""
        from app.services.file import FileService

        service = FileService()
        captured_cmd = None

        async def capture_shell(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"content", b""))
            mock_proc.returncode = 0
            return mock_proc

        with (
            patch("app.services.file.settings") as mock_settings,
            patch("asyncio.create_subprocess_shell", side_effect=capture_shell),
            patch("os.path.exists", return_value=True),
        ):
            mock_settings.ALLOW_SUDO = True
            try:
                await service.read_file(filename, sudo=True)
            except Exception:
                pass  # We only care about the captured command

        assert captured_cmd is not None, "subprocess_shell was not called"
        # The filename must appear shlex.quote'd — no bare single-quote injection
        expected_quoted = shlex.quote(filename)
        assert expected_quoted in captured_cmd, (
            f"Filename not properly quoted in command: {captured_cmd}"
        )

    @pytest.mark.parametrize("filename", DANGEROUS_FILENAMES)
    @pytest.mark.asyncio
    async def test_sudo_delete_quotes_path(self, filename: str):
        """sudo rm command must use shlex.quote on the path."""
        from app.services.file import FileService

        service = FileService()
        captured_cmd = None

        async def capture_shell(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0
            return mock_proc

        with (
            patch("app.services.file.settings") as mock_settings,
            patch("asyncio.create_subprocess_shell", side_effect=capture_shell),
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=False),
        ):
            mock_settings.ALLOW_SUDO = True
            try:
                await service.delete(filename, sudo=True)
            except Exception:
                pass

        assert captured_cmd is not None
        expected_quoted = shlex.quote(filename)
        assert expected_quoted in captured_cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python -m pytest tests/test_file_path_injection.py -v`
Expected: FAIL — captured command contains `'{filename}'` (single-quote wrapping) not `shlex.quote(filename)`

- [ ] **Step 3: Add shlex import and fix all sudo commands in file.py**

In `sandbox/app/services/file.py`, add import at top:
```python
import shlex
```

Fix line 144 (sudo read):
```python
# Before:
command = f"sudo cat '{file}'"
# After:
command = f"sudo cat {shlex.quote(str(file))}"
```

Fix line 223 (sudo mkdir):
```python
# Before:
mkdir_cmd = f"sudo mkdir -p '{parent_dir}'"
# After:
mkdir_cmd = f"sudo mkdir -p {shlex.quote(str(parent_dir))}"
```

Fix line 246 (sudo write — `temp_file` from mkstemp is safe, only `file` needs quoting):
```python
# Before:
command = f"sudo bash -c \"cat {temp_file} {mode} '{file}'\""
# After:
command = f"sudo bash -c 'cat {temp_file} {mode} {shlex.quote(str(file))}'"
```

> **Note on line 246:** `temp_file` comes from `tempfile.mkstemp()` (safe path, no metacharacters).
> `mode` is hardcoded `">"` or `">>"` (line 220). Only `file` is user-controlled and needs quoting.
> Do NOT double-nest `shlex.quote()` — it creates fragile escaping that is hard to reason about.

Fix line 438 (sudo delete):
```python
# Before:
command = f"sudo rm -rf -- '{path}'"
# After:
command = f"sudo rm -rf -- {shlex.quote(str(path))}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python -m pytest tests/test_file_path_injection.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run sandbox linting**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python -m ruff check app/services/file.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add sandbox/app/services/file.py sandbox/tests/test_file_path_injection.py
git commit -m "fix(security): prevent shell injection via filenames in sudo operations

Replaces single-quote f-string interpolation with shlex.quote() on all
sudo file commands (read, write, mkdir, delete). A filename containing
a single-quote could break quoting and inject arbitrary shell commands.

Ref: SEC-003"
```

---

## Task 3: Require Sandbox API Secret in Production (SEC-004)

**Files:**
- Modify: `sandbox/app/core/config.py:25`
- Create: `sandbox/tests/test_auth_enforcement.py`

> **Context:** The sandbox `Settings` class at `sandbox/app/core/config.py` extends `BaseSettings`
> from `pydantic_settings`. It currently has NO `ENVIRONMENT` field. We must add it.
> The class already uses `@field_validator` (line 94) so `@model_validator` is compatible.

- [ ] **Step 1: Write the failing test**

```python
# sandbox/tests/test_auth_enforcement.py
import pytest


class TestSandboxAuthEnforcement:
    def test_production_requires_secret(self):
        """In production, missing SANDBOX_API_SECRET must raise."""
        from app.core.config import Settings as SandboxSettings

        with pytest.raises(ValueError, match="SANDBOX_API_SECRET.*required"):
            SandboxSettings(
                SANDBOX_ENVIRONMENT="production",
                SANDBOX_API_SECRET=None,
            )

    def test_development_allows_missing_secret(self):
        """In development, missing secret is allowed with a warning."""
        from app.core.config import Settings as SandboxSettings

        # Should not raise
        settings = SandboxSettings(
            SANDBOX_ENVIRONMENT="development",
            SANDBOX_API_SECRET=None,
        )
        assert settings.SANDBOX_API_SECRET is None

    def test_default_environment_is_development(self):
        """Default environment must be development (safe fallback)."""
        from app.core.config import Settings as SandboxSettings

        settings = SandboxSettings()
        assert settings.SANDBOX_ENVIRONMENT == "development"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python -m pytest tests/test_auth_enforcement.py -v`
Expected: FAIL — `SANDBOX_ENVIRONMENT` field does not exist yet

- [ ] **Step 3: Add SANDBOX_ENVIRONMENT field and startup validation to sandbox config**

In `sandbox/app/core/config.py`:

Add `model_validator` to the imports on line 2:
```python
from pydantic import field_validator, model_validator
```

Add the `SANDBOX_ENVIRONMENT` field after the `LOG_LEVEL` field (after line 32):
```python
    # Deployment environment — controls security validation
    SANDBOX_ENVIRONMENT: str = "development"
```

Add the validator after the existing `assemble_cors_origins` validator (after line 101):
```python
    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        """Refuse to start without SANDBOX_API_SECRET in non-development environments."""
        if self.SANDBOX_ENVIRONMENT != "development" and not self.SANDBOX_API_SECRET:
            raise ValueError(
                "SANDBOX_API_SECRET is required in production. "
                "Set it via environment variable to authenticate sandbox API requests."
            )
        return self
```

> **Note:** Field is named `SANDBOX_ENVIRONMENT` (not `ENVIRONMENT`) to avoid
> collision with the common `ENVIRONMENT` env var that may be set system-wide.
> The `case_sensitive = True` config (line 104) means env var names must match exactly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/sandbox && python -m pytest tests/test_auth_enforcement.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add sandbox/app/core/config.py sandbox/tests/test_auth_enforcement.py
git commit -m "fix(security): require SANDBOX_API_SECRET in production

Adds SANDBOX_ENVIRONMENT field and model_validator that refuses to start
the sandbox in non-development environments without SANDBOX_API_SECRET.
Previously, the middleware silently allowed unauthenticated access.

Ref: SEC-004"
```

---

## Task 4: Restrict Sandbox CORS Origins (SEC-006)

**Files:**
- Modify: `sandbox/app/core/config.py`
- Modify: `sandbox/app/main.py:58`

- [ ] **Step 1: Add CORS origin configuration to sandbox config**

In `sandbox/app/core/config.py`:

```python
# Replace the existing ORIGINS field:
# Before:
ORIGINS: list[str] = ["*"]
# After:
ORIGINS: list[str] = ["http://backend:8000", "http://localhost:8000"]
```

- [ ] **Step 2: Verify CORS middleware uses the setting**

Read `sandbox/app/main.py:58-64` — already uses `settings.ORIGINS`. No change needed in main.py.

- [ ] **Step 3: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add sandbox/app/core/config.py
git commit -m "fix(security): restrict sandbox CORS to backend origin only

Replaces allow_origins=['*'] with specific backend URLs. The sandbox
should only accept requests from the backend service, not arbitrary
web pages on the same network.

Ref: SEC-006"
```

---

## Task 5: Create Central DOMPurify Sanitization Utility (SEC-010/011/013)

**Files:**
- Create: `frontend/src/utils/sanitize.ts`
- Create: `frontend/src/__tests__/utils/sanitize.test.ts`

> **Prerequisite:** `dompurify` is in `package.json` (^3.3.3) but `@types/dompurify` is NOT.
> DOMPurify 3.x ships its own types, so `@types/dompurify` is not needed. However, if
> `bun run type-check` fails with "Could not find a declaration file for module 'dompurify'",
> run: `cd frontend && bun add -D @types/dompurify`

- [ ] **Step 1: Write the test for the sanitization utility**

```typescript
// frontend/src/__tests__/utils/sanitize.test.ts
import { describe, it, expect } from 'vitest'
import { sanitizeHtml } from '@/utils/sanitize'

describe('sanitizeHtml', () => {
  it('strips script tags', () => {
    const dirty = '<p>Hello</p><script>alert("xss")</script>'
    expect(sanitizeHtml(dirty)).toBe('<p>Hello</p>')
  })

  it('strips onerror handlers', () => {
    const dirty = '<img src=x onerror="alert(1)">'
    const result = sanitizeHtml(dirty)
    expect(result).not.toContain('onerror')
  })

  it('preserves safe HTML', () => {
    const safe = '<p>Hello <strong>world</strong></p>'
    expect(sanitizeHtml(safe)).toBe(safe)
  })

  it('preserves markdown-rendered HTML', () => {
    const markdown = '<h1>Title</h1><ul><li>Item</li></ul><pre><code>code</code></pre>'
    expect(sanitizeHtml(markdown)).toBe(markdown)
  })

  it('strips javascript: URLs', () => {
    const dirty = '<a href="javascript:alert(1)">click</a>'
    const result = sanitizeHtml(dirty)
    expect(result).not.toContain('javascript:')
  })

  it('handles empty input', () => {
    expect(sanitizeHtml('')).toBe('')
  })

  it('handles non-string input gracefully', () => {
    // DOMPurify handles this, but we guard at our layer
    expect(sanitizeHtml(undefined as unknown as string)).toBe('')
    expect(sanitizeHtml(null as unknown as string)).toBe('')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run vitest run src/__tests__/utils/sanitize.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Create the sanitization utility**

```typescript
// frontend/src/utils/sanitize.ts
import DOMPurify from 'dompurify'

/**
 * Sanitize HTML string using DOMPurify.
 * Use this before any v-html binding as defense-in-depth.
 *
 * DOMPurify is already in package.json (^3.3.3) but was not
 * imported anywhere — this centralizes all sanitization.
 */
export function sanitizeHtml(dirty: string): string {
  if (!dirty || typeof dirty !== 'string') return ''
  return DOMPurify.sanitize(dirty)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run vitest run src/__tests__/utils/sanitize.test.ts`
Expected: ALL PASS

- [ ] **Step 5: Run type check**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add frontend/src/utils/sanitize.ts frontend/src/__tests__/utils/sanitize.test.ts
git commit -m "feat(security): add central DOMPurify sanitization utility

Creates sanitizeHtml() wrapper around DOMPurify for defense-in-depth
on all v-html bindings. DOMPurify was already in package.json but
never imported anywhere in src/.

Ref: SEC-010, SEC-011, SEC-013"
```

---

## Task 6: Add DOMPurify to FinalSummaryCard (SEC-011)

**Files:**
- Modify: `frontend/src/components/report/FinalSummaryCard.vue:3`

- [ ] **Step 1: Add sanitization to FinalSummaryCard**

In `frontend/src/components/report/FinalSummaryCard.vue`:

> **Note:** The original uses bare `defineProps` (no assignment). We change to
> `const props = defineProps<...>()` to access `props.htmlContent` in computed.
> This is a deliberate change required to reference the prop value.

```vue
<template>
  <div class="final-summary-card" data-testid="final-summary-card">
    <div class="final-summary-content markdown-content" v-html="safeHtml" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { sanitizeHtml } from '@/utils/sanitize'

const props = defineProps<{
  htmlContent: string
}>()

const safeHtml = computed(() => sanitizeHtml(props.htmlContent))
</script>
```

- [ ] **Step 2: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint:check`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add frontend/src/components/report/FinalSummaryCard.vue
git commit -m "fix(security): add DOMPurify defense-in-depth to FinalSummaryCard

htmlContent prop was rendered via v-html with no component-level
sanitization. DOMPurify sanitization now happens in the component
regardless of whether upstream callers already sanitize.

Ref: SEC-011"
```

---

## Task 7: Add DOMPurify to SkillFilePreview Markdown (SEC-013)

**Files:**
- Modify: `frontend/src/components/skill/SkillFilePreview.vue:35,136-143`

- [ ] **Step 1: Add sanitization to the rendered markdown computed**

In `frontend/src/components/skill/SkillFilePreview.vue`:

Add import:
```typescript
import { sanitizeHtml } from '@/utils/sanitize'
```

Modify the `renderedMarkdown` computed (around line 136):
```typescript
const renderedMarkdown = computed(() => {
  if (!isMarkdown.value) return ''
  const rawHtml = marked(displayContent.value, {
    breaks: true,
    gfm: true,
  })
  return sanitizeHtml(rawHtml as string)
})
```

- [ ] **Step 2: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint:check`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add frontend/src/components/skill/SkillFilePreview.vue
git commit -m "fix(security): sanitize marked() output in SkillFilePreview

marked() does not sanitize HTML by default. Skill files can be
uploaded externally, so unsanitized markdown with <script> or
event handlers would execute. Now passes through DOMPurify.

Ref: SEC-013"
```

---

## Task 8: Replace v-html with Safe Interpolation in SharePage (SEC-012)

**Files:**
- Modify: `frontend/src/pages/SharePage.vue:107`

> **Context:** The project uses `vue-i18n` (confirmed in `main.ts`, `SharePage.vue`, and 8+
> other files). `$t()` is available in templates. The `<i18n-t>` component from vue-i18n
> supports slot-based interpolation which is the canonical safe approach for embedding
> HTML elements inside translated strings.

- [ ] **Step 1: Replace v-html with `$t` + safe template interpolation**

In `frontend/src/pages/SharePage.vue`, replace the v-html div (line 107):

```vue
<!-- Before: -->
<div class="text-center text-[var(--text-primary)] whitespace-pre-line"
  v-html="$t('You are viewing a completed Pythinker task. Replay will start automatically in {countdown} seconds.', { countdown: `<strong>${countdown}</strong>` })">
</div>

<!-- After: Use $t with the countdown as a plain number, add <strong> outside -->
<div class="text-center text-[var(--text-primary)] whitespace-pre-line">
  {{ $t('You are viewing a completed Pythinker task. Replay will start automatically in {countdown} seconds.', { countdown }) }}
</div>
```

> **Why this works:** The `countdown` ref is a numeric value. By passing it directly
> (not wrapped in `<strong>` tags), the translation output is pure text — no HTML.
> Vue's `{{ }}` interpolation auto-escapes, so XSS is impossible. The `<strong>` styling
> can be achieved via CSS on the countdown number, or the bold can be dropped entirely
> since it's purely cosmetic. If bold is essential, wrap the entire div or use a `<span>`:
>
> ```vue
> {{ $t('You are viewing a completed Pythinker task. Replay will start automatically in') }}
> <strong>{{ countdown }}</strong>
> {{ $t('seconds.') }}
> ```

- [ ] **Step 2: Verify visual rendering**

Run dev server and navigate to a shared session URL. Verify the countdown text displays correctly.

- [ ] **Step 3: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/frontend && bun run type-check && bun run lint:check`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add frontend/src/pages/SharePage.vue
git commit -m "fix(security): replace v-html with safe interpolation in SharePage

The countdown display used v-html with an interpolated <strong> tag
inside a translation string. Replaced with safe {{ }} interpolation
to prevent any XSS risk from the translation pipeline.

Ref: SEC-012"
```

---

## Task 9: Add Ownership Check to Session Cancel (SEC-014)

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py:549-564`
- Create: `backend/tests/interfaces/api/test_session_cancel_authz.py`

> **Context:** `get_session_repository` exists in `backend/app/interfaces/dependencies.py:349`
> returning `MongoSessionRepository()`. `UserRole` exists at `backend/app/domain/models/user.py:7`.
> Neither `get_session_repository` nor `UserRole` is currently imported in `session_routes.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/interfaces/api/test_session_cancel_authz.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.domain.models.user import User, UserRole
from app.domain.models.session import Session


class TestSessionCancelAuthorization:
    """Cancel endpoint must verify session ownership."""

    @pytest.fixture
    def owner_user(self):
        return User(
            id="user-owner",
            fullname="Owner",
            email="owner@test.com",
            role=UserRole.USER,
            is_active=True,
        )

    @pytest.fixture
    def other_user(self):
        return User(
            id="user-other",
            fullname="Other",
            email="other@test.com",
            role=UserRole.USER,
            is_active=True,
        )

    @pytest.fixture
    def session(self, owner_user):
        session = MagicMock(spec=Session)
        session.session_id = "session-123"
        session.user_id = owner_user.id
        return session

    @pytest.mark.asyncio
    async def test_owner_can_cancel(self, owner_user, session):
        """Session owner can cancel their own session."""
        from app.interfaces.api.session_routes import cancel_session

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = session

        # Call function directly, passing ALL parameters including session_repo
        result = await cancel_session(
            session_id="session-123",
            current_user=owner_user,
            agent_service=agent_service,
            session_repo=session_repo,
        )
        agent_service.request_cancellation.assert_called_once_with("session-123")

    @pytest.mark.asyncio
    async def test_non_owner_cannot_cancel(self, other_user, session):
        """Non-owner must get 403 when cancelling another user's session."""
        from app.interfaces.api.session_routes import cancel_session
        from fastapi import HTTPException

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = session

        # Call function directly, passing ALL parameters including session_repo
        with pytest.raises(HTTPException) as exc_info:
            await cancel_session(
                session_id="session-123",
                current_user=other_user,
                agent_service=agent_service,
                session_repo=session_repo,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self, owner_user):
        """Cancelling a non-existent session must return 404."""
        from app.interfaces.api.session_routes import cancel_session
        from fastapi import HTTPException

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await cancel_session(
                session_id="nonexistent",
                current_user=owner_user,
                agent_service=agent_service,
                session_repo=session_repo,
            )
        assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && conda activate pythinker && pytest tests/interfaces/api/test_session_cancel_authz.py -v -p no:cov -o addopts=`
Expected: FAIL — `cancel_session` does not accept `session_repo` parameter yet

- [ ] **Step 3: Add imports and ownership check to cancel endpoint**

In `backend/app/interfaces/api/session_routes.py`:

**Step 3a:** Add imports at top of file (find existing import block):
```python
from app.domain.models.user import UserRole
from app.interfaces.dependencies import get_session_repository
```

**Step 3b:** Modify `cancel_session` (line 549):
```python
@router.post("/{session_id}/cancel", status_code=202)
async def cancel_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    session_repo=Depends(get_session_repository),
) -> dict[str, str]:
    """Request graceful cancellation of a running session."""
    # Verify ownership
    session = await session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this session")

    agent_service.request_cancellation(session_id)
    logger.info("Cancellation requested for session %s by user %s", session_id, current_user.id)
    return {"status": "cancelling", "session_id": session_id}
```

> **Note:** Using `session_repo=Depends(get_session_repository)` without type annotation
> avoids importing `MongoSessionRepository` in the routes layer. The dependency function
> returns the concrete type. For tests, we pass a mock directly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest tests/interfaces/api/test_session_cancel_authz.py -v -p no:cov -o addopts=`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add backend/app/interfaces/api/session_routes.py backend/tests/interfaces/api/test_session_cancel_authz.py
git commit -m "fix(security): add ownership check to session cancel endpoint

Any authenticated user could cancel any other user's session via
POST /{session_id}/cancel. Now verifies session.user_id matches
current_user.id (admins bypass the check).

Ref: SEC-014"
```

---

## Task 10: Validate JWT Secret at Startup (SEC-015)

**Files:**
- Modify: `backend/app/core/config.py` (add validator to composed `Settings` class)
- Create: `backend/tests/core/test_config_auth_validation.py`

> **IMPORTANT:** `JWTSettingsMixin` is a **plain class** (not a Pydantic model). `@model_validator`
> only works on Pydantic `BaseModel`/`BaseSettings` subclasses. Placing the decorator on the
> mixin will fail at import time. The validator must be added to the **composed `Settings` class**
> in `backend/app/core/config.py` which inherits from `BaseSettings`.
>
> The `Settings` class at `config.py:77` inherits from `JWTSettingsMixin`, `AuthSettingsMixin`,
> and `BaseSettings`. Pydantic validators placed on `Settings` can access fields from all mixins.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/core/test_config_auth_validation.py
import os
import pytest


class TestJWTSecretValidation:
    def test_password_auth_requires_jwt_secret(self):
        """Password auth provider with no JWT secret must fail."""
        # Use the composed Settings class (not the mixin) since validators live there
        from app.core.config import Settings

        with pytest.raises(ValueError, match="jwt_secret_key.*required"):
            Settings(
                auth_provider="password",
                jwt_secret_key=None,
                # Provide minimal required fields to avoid other validation errors
                mongodb_uri="mongodb://localhost:27017",
            )

    def test_none_auth_allows_missing_jwt_secret(self):
        """Auth provider 'none' does not require JWT secret."""
        from app.core.config import Settings

        # Should not raise
        config = Settings(
            auth_provider="none",
            jwt_secret_key=None,
            mongodb_uri="mongodb://localhost:27017",
        )
        assert config.jwt_secret_key is None

    def test_jwt_secret_set_passes_validation(self):
        """Valid JWT secret passes regardless of auth provider."""
        from app.core.config import Settings

        config = Settings(
            auth_provider="password",
            jwt_secret_key="super-secret-key-1234",
            mongodb_uri="mongodb://localhost:27017",
        )
        assert config.jwt_secret_key == "super-secret-key-1234"
```

> **Note:** Tests construct `Settings` directly with overrides. If Settings loads from `.env`
> and picks up existing `JWT_SECRET_KEY`, use `monkeypatch.delenv("JWT_SECRET_KEY", raising=False)`
> in a fixture. The `mongodb_uri` is provided to satisfy any other validators.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && conda activate pythinker && pytest tests/core/test_config_auth_validation.py -v -p no:cov -o addopts=`
Expected: `test_password_auth_requires_jwt_secret` FAILS (no validation exists)

- [ ] **Step 3: Add model_validator to the composed Settings class**

In `backend/app/core/config.py`, add a `@model_validator(mode="after")` to the `Settings` class.

First, add `model_validator` to the pydantic import (line 23):
```python
from pydantic import computed_field, model_validator
```

Then add the validator method inside the `Settings` class body (after the existing fields/methods):
```python
    @model_validator(mode="after")
    def validate_jwt_secret_for_auth(self) -> "Settings":
        """Refuse to start if auth is enabled but JWT secret is missing."""
        if self.auth_provider != "none" and not self.jwt_secret_key:
            raise ValueError(
                "jwt_secret_key is required when auth_provider is not 'none'. "
                "Set JWT_SECRET_KEY environment variable."
            )
        return self
```

> **Why on Settings, not JWTSettingsMixin:** The mixin is a plain class used only
> for field grouping. Pydantic discovers `@model_validator` only on `BaseModel`
> subclasses. `Settings(BaseSettings)` is the concrete model.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest tests/core/test_config_auth_validation.py -v -p no:cov -o addopts=`
Expected: ALL PASS

- [ ] **Step 5: Verify existing tests still pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest tests/ -x --timeout=30 -p no:cov -o addopts=`
Expected: No regressions. If Settings creation fails in other tests because they don't set
`JWT_SECRET_KEY`, those tests must either set it or use `auth_provider="none"`.

- [ ] **Step 6: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add backend/app/core/config.py backend/tests/core/test_config_auth_validation.py
git commit -m "fix(security): validate JWT secret at startup when auth is enabled

JWTs were signed with None as the secret when jwt_secret_key was unset.
Now raises ValueError at startup if auth_provider != 'none' and
jwt_secret_key is missing. Validator placed on composed Settings class.

Ref: SEC-015"
```

---

## Task 11: Use Constant-Time Comparison for Sandbox Callback Token (SEC-016)

**Files:**
- Modify: `backend/app/interfaces/api/sandbox_callback_routes.py:52`

- [ ] **Step 1: Fix the comparison**

In `backend/app/interfaces/api/sandbox_callback_routes.py:52`:

```python
import secrets

async def verify_sandbox_callback_token(
    x_sandbox_callback_token: str = Header(...),
) -> str:
    """Validate the sandbox callback token."""
    settings = get_settings()
    expected = settings.sandbox_callback_token
    if not expected or not secrets.compare_digest(x_sandbox_callback_token, expected):
        raise HTTPException(status_code=401, detail="Invalid sandbox callback token")
    return x_sandbox_callback_token
```

- [ ] **Step 2: Verify import and lint**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && ruff check app/interfaces/api/sandbox_callback_routes.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add backend/app/interfaces/api/sandbox_callback_routes.py
git commit -m "fix(security): use constant-time comparison for sandbox callback token

Plain != comparison is vulnerable to timing oracle attacks. Uses
secrets.compare_digest() matching the pattern already used in
metrics_routes.py.

Ref: SEC-016"
```

---

## Task 12: Replace Admin Role Magic String with Enum (SEC-017)

**Files:**
- Modify: `backend/app/interfaces/api/auth_routes.py:232,249`

- [ ] **Step 1: Add UserRole import and fix comparisons**

In `backend/app/interfaces/api/auth_routes.py`:

**Step 1a:** Find the existing import `from app.domain.models.user import User` (line 10) and change to:
```python
from app.domain.models.user import User, UserRole
```

> **Note:** `UserRole` is NOT currently imported in this file. The import line currently only
> imports `User`. You MUST change the existing import to include `UserRole`.

Fix line 232:
```python
# Before:
if current_user.role != "admin":
# After:
if current_user.role != UserRole.ADMIN:
```

Fix line 249:
```python
# Before:
if current_user.role != "admin":
# After:
if current_user.role != UserRole.ADMIN:
```

- [ ] **Step 2: Run lint**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && ruff check app/interfaces/api/auth_routes.py`
Expected: PASS

- [ ] **Step 3: Verify existing admin auth tests still pass**

Run: `cd /Users/panda/Desktop/Projects/Pythinker/backend && pytest tests/interfaces/api/test_admin_authorization.py -v -p no:cov -o addopts=`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add backend/app/interfaces/api/auth_routes.py
git commit -m "fix(security): replace admin role magic string with UserRole.ADMIN enum

Raw string comparison 'admin' replaced with UserRole.ADMIN enum,
matching the pattern already used in dependencies.py:523.

Ref: SEC-017"
```

---

## Task 13: Weak Default Supervisor Password (SEC-009)

**Files:**
- Modify: `sandbox/app/core/config.py:28-29`

> **Prerequisite:** Task 3 must be completed first. After Task 3, `sandbox/app/core/config.py`
> already has `from pydantic import field_validator, model_validator` and a `validate_production_secret`
> model_validator. This task adds a second model_validator to the same class. Pydantic v2 supports
> multiple `@model_validator(mode="after")` on the same class — they run in definition order.

- [ ] **Step 1: Generate random password when not set**

In `sandbox/app/core/config.py`:

Add `secrets` import at top (after the existing imports):
```python
import secrets as _secrets
```

Change the default password (line 29):
```python
# Before:
SUPERVISOR_RPC_PASSWORD: str = "supervisor-dev-password"
# After:
SUPERVISOR_RPC_PASSWORD: str = ""
```

Add a second model_validator after the `validate_production_secret` validator added in Task 3:
```python
    @model_validator(mode="after")
    def generate_supervisor_password(self) -> "Settings":
        """Generate random supervisor password if not explicitly configured."""
        if not self.SUPERVISOR_RPC_PASSWORD or self.SUPERVISOR_RPC_PASSWORD == "supervisor-dev-password":
            import logging
            self.SUPERVISOR_RPC_PASSWORD = _secrets.token_urlsafe(24)
            logging.getLogger(__name__).warning(
                "SUPERVISOR_RPC_PASSWORD not set or using default — generated random password. "
                "Set SUPERVISOR_RPC_PASSWORD environment variable to use a fixed password."
            )
        return self
```

- [ ] **Step 2: Verify sandbox starts with random password**

Run: `cd /Users/panda/Desktop/Projects/Pythinker && docker compose -f docker-compose-development.yml up sandbox -d && docker logs pythinker-sandbox-1 2>&1 | grep -i supervisor`
Expected: Warning about generated random password OR no error if password was explicitly set.

- [ ] **Step 3: Commit**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
git add sandbox/app/core/config.py
git commit -m "fix(security): generate random supervisor password when not set

Default password 'supervisor-dev-password' ships in source code.
Now generates a random token_urlsafe(24) password at startup if
not explicitly configured. Logs a warning to aid debugging.

Ref: SEC-009"
```

---

## Verification Checklist

After completing all tasks:

- [ ] **Backend lint:** `cd backend && ruff check . && ruff format --check .`
- [ ] **Backend tests:** `cd backend && conda activate pythinker && pytest tests/ -x --timeout=60`
- [ ] **Frontend lint:** `cd frontend && bun run lint:check`
- [ ] **Frontend type-check:** `cd frontend && bun run type-check`
- [ ] **Frontend tests:** `cd frontend && bun run test:run`
- [ ] **Docker build:** `docker compose -f docker-compose-development.yml build`
- [ ] **Smoke test:** Start stack, create session, run agent task with browser and shell tools

---

## Deferred Items (Not in This Plan)

These SEC items require more significant design work and are deferred to separate plans:

| Item | Reason for Deferral |
|------|-------------------|
| SEC-002 (Shell command injection) | Requires shell feature compatibility layer — needs separate design |
| SEC-005 (Rate limiting) | Requires rate limiter middleware selection and configuration |
| SEC-007 (Per-operation credentials) | Requires new sandbox API endpoint and tool refactoring |
| SEC-008 (Seccomp consistency) | Requires seccomp profile testing across both manager paths |
