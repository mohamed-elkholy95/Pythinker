# Repo Issues And Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the current failing backend test, resolve the open actionable GitHub security alerts, and bring the repo back to a clean documented validation state.

**Architecture:** Fix runtime and validation breakage before bulk alert cleanup. First align `DockerSandbox._create_task()` and its tests with the current settings and sandbox security contract, then patch the shipped security findings (`cryptography` and sandbox path handling), then clean up the 40 test-only CodeQL alerts by normalizing test fixtures instead of changing product behavior.

**Tech Stack:** Python backend via `uv`, FastAPI, pytest, Ruff, Docker sandbox runtime, Vue/Vite frontend via Bun and Vitest, GitHub CodeQL, Dependabot.

---

## Chunk 1: Restore A Green Backend Test Suite

### Task 1: Fix The Only Failing Backend Test

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- Modify: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py`
- Possibly Modify: `backend/app/domain/services/sandbox_security_policy_service.py`
- Test: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py`

- [ ] **Step 1: Reproduce the failing test**

Run: `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py::TestDockerSandboxCreateTaskSecurityPolicy::test_create_task_uses_policy_service_security_options -v`

Expected: FAIL with `AttributeError: 'types.SimpleNamespace' object has no attribute 'sandbox_enable_vnc'`, wrapped as `Exception: Failed to create Docker sandbox: ...`.

- [ ] **Step 2: Align the test fixture with the current `_create_task()` settings contract**

Inspect the settings reads in `DockerSandbox._create_task()`. The test fixture currently omits newer settings that the method now accesses, including:

- `sandbox_enable_vnc`
- `supervisor_rpc_username`
- `supervisor_rpc_password`
- `sandbox_log_level`
- `sandbox_tz`
- `sandbox_shell_structured_markers`
- `sandbox_runtime_api_host`
- `sandbox_callback_token`
- `sandbox_llm_proxy_key`
- token/proxy settings that are treated as optional branches

Preferred change: expand the `SimpleNamespace` in the test so it mirrors the real settings surface used by `_create_task()`. Only add `getattr(..., default)` fallbacks in production code for values that are truly optional at runtime.

- [ ] **Step 3: Resolve the seccomp expectation mismatch**

Current code path:

- consults `get_sandbox_security_policy()`
- applies `cap_drop`
- applies `cap_add`
- applies `tmpfs`
- hardcodes `security_opt = ["no-new-privileges:true"]`
- explicitly omits seccomp propagation

Decision to make after reproducing the test:

- If dynamic containers can receive a valid absolute seccomp profile path from the backend runtime, append the policy-derived seccomp option and keep the test asserting it.
- If dynamic containers still cannot safely receive seccomp via the Docker API in this environment, narrow the test to the supported hardening contract and add a separate regression test documenting the intentional omission.

Do not guess. Preserve the real runtime contract after verifying what the Docker client can accept from this process.

- [ ] **Step 4: Re-run the focused sandbox tests**

Run: `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py -v`

Expected: PASS

- [ ] **Step 5: Re-run backend validation**

Run:

- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt ruff check .`
- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt ruff format --check .`
- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/`

Expected: no failing backend tests remain.

## Chunk 2: Fix The Open Shipped Security Findings

### Task 2: Patch The Open Non-Test Security Alerts

**Files:**
- Modify: `sandbox/app/services/shell.py`
- Test: `sandbox/tests/test_service_path_normalization.py`
- Test: `sandbox/tests/test_shell_path_validation.py`
- Possibly Test: `sandbox/tests/test_api_file.py`
- Modify: `backend/requirements.txt`
- Modify: `sandbox/requirements.runtime.txt`

- [ ] **Step 1: Reproduce and inspect the sandbox path-injection alert**

Reference: GitHub code scanning alert `#337` on `sandbox/app/services/shell.py:164`.

Investigate the `exec_dir` flow in `ShellService.exec_command()`. Today it:

- resolves `~`
- converts to absolute path
- creates `/workspace/**` paths

But it does not prove that the normalized path stays inside an allowed root.

- [ ] **Step 2: Reuse the existing path-normalization model**

Use the same allowlist and normalization principles already present in the sandbox file service rather than inventing a second policy.

Implementation target:

- normalize with `realpath`
- reject traversal outside allowed roots
- keep `/workspace` creation only after the path is proven safe
- preserve the legacy home-alias behavior already covered by tests

- [ ] **Step 3: Add regression coverage for shell path validation**

Extend or add tests for:

- allowed workspace path
- `/workspace/subdir` auto-create
- home alias resolution
- traversal like `../`
- blocked absolute paths such as `/etc`
- any symlink/realpath escape already represented in sandbox tests

Run in the prepared sandbox test environment: `cd sandbox && pytest tests/test_service_path_normalization.py tests/test_shell_path_validation.py -v`

Expected: PASS

- [ ] **Step 4: Upgrade the vulnerable runtime dependency**

Reference: open Dependabot alert `#76` for `cryptography`, first patched in `46.0.6`.

Run:

- update `backend/requirements.txt` to require `cryptography>=46.0.6,<47.0.0`
- update `sandbox/requirements.runtime.txt` to pin `cryptography==46.0.6`

Rationale: the open alert is on the shipped sandbox manifest, but the backend dev/test environment should not keep a lower vulnerable floor than the sandbox runtime.

- [ ] **Step 5: Re-run focused validation**

Run:

- `python3 - <<'PY'`
- `from pathlib import Path`
- `import re`
- `backend = Path("backend/requirements.txt").read_text()`
- `sandbox = Path("sandbox/requirements.runtime.txt").read_text()`
- `assert re.search(r"^cryptography>=46\\.0\\.6,<47\\.0\\.0$", backend, re.M)`
- `assert re.search(r"^cryptography==46\\.0\\.6$", sandbox, re.M)`
- `PY`
- `cd sandbox && pytest tests/test_service_path_normalization.py tests/test_shell_path_validation.py -v`

Expected: PASS

## Chunk 3: Close The 40 Test-Only CodeQL Alerts

### Task 3: Replace Unsafe Test Fixtures Without Weakening Coverage

**Files:**
- Modify: `backend/tests/domain/services/agents/test_url_verification.py`
- Modify: `backend/tests/domain/services/test_memory_manager.py`
- Modify: `backend/tests/domain/services/tools/test_deal_scraper.py`
- Modify: `backend/tests/domain/models/test_url_verification.py`
- Modify: `backend/tests/domain/utils/test_url_filters.py`
- Modify: `backend/tests/domain/services/agents/test_task_state_manager.py`
- Modify: `backend/tests/domain/models/test_url_verification_models.py`
- Modify: `backend/tests/unit/domain/services/agents/test_step_executor.py`
- Modify: `backend/tests/unit/domain/models/test_plan.py`
- Modify: `backend/tests/domain/services/tools/test_command_formatter.py`
- Modify: `backend/tests/domain/services/tools/test_browser_models.py`
- Modify: `backend/tests/domain/services/test_output_verifier.py`
- Modify: `backend/tests/domain/services/test_critic.py`
- Modify: `backend/tests/domain/services/agents/test_verifier_evidence.py`
- Modify: `backend/tests/domain/services/agents/test_content_safety.py`
- Modify: `backend/tests/domain/models/test_structured_outputs.py`
- Modify: `backend/tests/domain/models/test_research_phase.py`
- Possibly Create: `backend/tests/helpers/url_fixtures.py`

- [ ] **Step 1: Group the alerting tests by intent**

Current hotspot distribution:

- `backend/tests/domain/services/agents/test_url_verification.py`: 10 alerts
- `backend/tests/domain/services/test_memory_manager.py`: 7 alerts
- `backend/tests/domain/services/tools/test_deal_scraper.py`: 4 alerts
- remaining 19 alerts spread across 14 files

Before editing, classify them into:

- allowed-host fixtures
- malicious lookalike-host fixtures
- negative browser/search/redirect fixtures

- [ ] **Step 2: Introduce shared safe URL builders**

If repeated patterns justify it, add a helper module such as `backend/tests/helpers/url_fixtures.py` that can generate:

- canonical allowed URLs
- malicious lookalike URLs
- blocked URL variants

Goal: preserve the same behavioral assertions without embedding allowlisted hostnames as raw unparsed substrings in attacker-controlled fixture strings.

- [ ] **Step 3: Update the high-volume files first**

Start with:

- `backend/tests/domain/services/agents/test_url_verification.py`
- `backend/tests/domain/services/test_memory_manager.py`
- `backend/tests/domain/services/tools/test_deal_scraper.py`

Run after each file or cluster:

- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/domain/services/agents/test_url_verification.py -v`
- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/domain/services/test_memory_manager.py -v`
- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/domain/services/tools/test_deal_scraper.py -v`

Expected: PASS

- [ ] **Step 4: Update the remaining single-file alerts**

Apply the same fixture normalization pattern to the remaining 14 files. Keep the tests semantically identical; do not delete the negative cases that made CodeQL complain.

- [ ] **Step 5: Re-run the full backend suite**

Run: `cd backend && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/`

Expected: PASS

- [ ] **Step 6: Re-query GitHub code scanning**

Run: `gh api -H 'Accept: application/vnd.github+json' '/repos/mohamed-elkholy95/Pythinker/code-scanning/alerts?state=open&per_page=100'`

Expected:

- the 40 `py/incomplete-url-substring-sanitization` alerts are gone, or
- the remaining alerts are explicitly justified and ready for dismissal

## Chunk 4: Final Verification And GitHub Recheck

### Task 4: Confirm The Repo Is Clean After The Fixes

**Files:**
- Modify: `docs/superpowers/plans/2026-03-27-fix-all-issues-security-tests.md`

- [ ] **Step 1: Re-run the documented validation commands**

Run:

- `cd frontend && bun run lint:check && bun run type-check`
- `cd frontend && bun run test:run`
- `cd backend && uv run --no-progress --with-requirements requirements-dev.txt ruff check . && uv run --no-progress --with-requirements requirements-dev.txt ruff format --check . && uv run --no-progress --with-requirements requirements-dev.txt pytest tests/`

Expected:

- frontend green
- backend green
- no new failing tests introduced

- [ ] **Step 2: Re-query GitHub issue and security surfaces**

Run:

- `gh issue list --repo mohamed-elkholy95/Pythinker --state all --limit 1000`
- `gh api -H 'Accept: application/vnd.github+json' '/repos/mohamed-elkholy95/Pythinker/dependabot/alerts?state=open&per_page=100'`
- `gh api -H 'Accept: application/vnd.github+json' '/repos/mohamed-elkholy95/Pythinker/code-scanning/alerts?state=open&per_page=100'`
- `gh api -H 'Accept: application/vnd.github+json' '/repos/mohamed-elkholy95/Pythinker/secret-scanning/alerts?state=open&per_page=100'`

Expected:

- no open normal GitHub issues unless new ones were created during the work
- Dependabot alert resolved
- non-test CodeQL alert resolved
- test-only CodeQL alerts resolved or explicitly triaged
- no open secret-scanning alerts

- [ ] **Step 3: Record residual environment-dependent skips separately from failures**

Document, but do not treat as regressions:

- backend/API-dependent integration skips
- browser/CDP-dependent skips
- Redis/Mongo-dependent skips
- Playwright browser-install skips

These were part of the baseline run and should not be conflated with failing tests.
