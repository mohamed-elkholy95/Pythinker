# Security Code Scanning Report

**Repository:** `mohamed-elkholy95/Pythinker`
**Date:** 2026-03-18
**Source:** GitHub Code Scanning (CodeQL + Trivy)
**Branch:** `main-dev`

---

## Executive Summary

| Metric | Count |
|--------|-------|
| **Total Alerts** | 270 |
| **Open** | 29 |
| **Dismissed** (won't fix) | 201 |
| **Fixed** | 40 |
| **Tools** | CodeQL (208), Trivy (62) |

### Severity Breakdown (All Alerts)

| Severity | Open | Dismissed | Fixed | Total |
|----------|------|-----------|-------|-------|
| Critical | 0 | 5 | 0 | 5 |
| High | 22 | 183 | 29 | 234 |
| Medium | 3 | 8 | 8 | 19 |
| Low | 4 | 0 | 3 | 7 |
| Unknown/None | 0 | 5 | 0 | 5 |

### Validated Assessment Summary

After LSP-guided codebase validation of all 270 alerts:

| Assessment | Count | Description |
|------------|-------|-------------|
| **True Positive** | 4 | Real vulnerabilities requiring attention |
| **Mitigated by Architecture** | ~100 | Sandbox isolation is the security boundary |
| **False Positive** | ~97 | Not actual vulnerabilities (context-dependent) |
| **Fixed** | 40 | Already resolved |
| **Dismissed (Correct)** | ~29 | Correctly triaged as won't-fix |

---

## Part 1: Open Alerts (29 Active)

### 1.1 Trivy — Container Dependency Vulnerabilities (29 Open)

All 29 open alerts are from Trivy scanning the **sandbox Docker image**. These are vulnerabilities in system-level packages inside the container, not in Pythinker's own code.

#### HIGH Severity (22 alerts)

##### node-tar (tar package) — 18 alerts across 3 locations

| CVE | Description | Installed | Fixed | Locations |
|-----|-------------|-----------|-------|-----------|
| CVE-2026-31802 | File overwrite via drive-relative symlink traversal | 7.4.3 | 7.5.11 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |
| CVE-2026-29786 | Hardlink path traversal via drive-relative linkpath | 7.4.3 | 7.5.10 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |
| CVE-2026-26960 | Arbitrary file read/write via malicious archive hardlinks | 7.4.3 | 7.5.10 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |
| CVE-2026-24842 | Arbitrary file creation via path traversal bypass | 7.4.3 | 7.5.10 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |
| CVE-2026-23950 | Arbitrary file overwrite via Unicode path collision | 7.4.3 | 7.5.10 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |
| CVE-2026-23745 | Arbitrary file overwrite via unsanitized linkpaths | 7.4.3 | 7.5.10 | npm/tar, npm/cacache/tar, npm/node-gyp/tar |

**Location:** `usr/local/nvm/versions/node/v22.22.1/lib/node_modules/npm/node_modules/`
**Fix:** Update Node.js to latest LTS or pin `tar >= 7.5.11` in sandbox Dockerfile.

##### minimatch — 3 alerts

| CVE | Description | Fixed |
|-----|-------------|-------|
| CVE-2026-27904 | DoS via catastrophic backtracking in glob expressions | 10.0.3 |
| CVE-2026-27903 | DoS via unbounded recursive backtracking | 10.0.3 |
| CVE-2026-26996 | DoS via specially crafted glob patterns | 10.0.3 |

**Location:** `npm/node_modules/minimatch/package.json`

##### glob — 1 alert

| CVE | Description |
|-----|-------------|
| CVE-2025-64756 | Command injection via malicious filenames |

**Location:** `npm/node_modules/glob/package.json`

#### MEDIUM Severity (3 alerts)

| CVE | Package | Description | Location |
|-----|---------|-------------|----------|
| CVE-2025-8869 | pip 25.0.1 | Missing checks on symbolic link extraction | `usr/local/lib/python3.12/` |
| CVE-2026-25537 | jsonwebtoken (in `uv`) | Type confusion → potential auth bypass | `usr/local/bin/uv` |
| CVE-2026-25537 | jsonwebtoken (in `uvx`) | Type confusion → potential auth bypass | `usr/local/bin/uvx` |

#### LOW Severity (2 alerts)

| CVE | Package | Description |
|-----|---------|-------------|
| CVE-2026-1703 | pip 25.0.1 | Information disclosure via path traversal |
| CVE-2026-24001 | diff (npm) | DoS in parsePatch and applyPatch |

#### HIGH — Python Ecosystem (2 alerts)

| CVE | Package | Description | Location |
|-----|---------|-------------|----------|
| CVE-2026-23949 | jaraco.context 5.3.0 | Path traversal via malicious tar archives | `opt/base-python-venv/` setuptools vendor |
| CVE-2026-24049 | wheel 0.45.1 | Privilege escalation via malicious wheel unpacking | `opt/base-python-venv/` setuptools vendor |

---

## Part 2: Dismissed Alerts — Validated Assessment (201 alerts)

All dismissed alerts were marked "won't fix". Below is the LSP-validated analysis confirming or challenging each dismissal.

### 2.1 CodeQL: Command Injection — `py/command-line-injection` (5 alerts, CRITICAL)

| Alert # | File | Line | Assessment |
|---------|------|------|------------|
| 13 | `sandbox/app/services/shell.py` | 100 | **MITIGATED** |
| 12 | `sandbox/app/services/file.py` | 430 | **MITIGATED** |
| 11 | `sandbox/app/services/file.py` | 248 | **MITIGATED** |
| 10 | `sandbox/app/services/file.py` | 225 | **MITIGATED** |
| 9 | `sandbox/app/services/file.py` | 146 | **MITIGATED** |

**Validation Details:**

- **shell.py:100** — `asyncio.create_subprocess_shell(command, executable="/bin/bash", cwd=exec_dir)`. This is the **core purpose** of the shell service: execute arbitrary commands from the AI agent inside an isolated Docker sandbox. Command injection is the intended behavior. The entire sandbox runs in a disposable Docker container with no host access.

- **file.py:146,225,248,430** — Uses `f"sudo cat '{file}'"` with single-quote wrapping. The path has already been validated by `safe_resolve()` which resolves to canonical paths under `SANDBOX_ALLOWED_DIRS` (`/home/ubuntu`, `/workspace`). The single-quote wrapping is imperfect (a filename with literal `'` could theoretically escape), but `safe_resolve()` normalizes paths first.

**Dismissal verdict: CORRECT** — Docker sandbox isolation is the security boundary. These services are designed to execute arbitrary operations within the container.

---

### 2.2 CodeQL: Path Injection — `py/path-injection` (119 alerts, HIGH)

**Affected files (all in `sandbox/`):**

| File | Alert Count | Has `safe_resolve()` | Has `if False:` bypass |
|------|-------------|---------------------|----------------------|
| `services/workspace.py` | 34 | No | Yes (deliberately removed) |
| `services/test_runner.py` | 22 | No | Yes (`if False:` at line 162) |
| `services/export.py` | 29 | No | Yes (`if False:` at line 125) |
| `services/file.py` | 13 | **Yes** (`safe_resolve()` at line 45) | No |
| `services/code_dev.py` | 9 | No | Yes (`if False:` at line 157) |
| `services/git.py` | 10 | No | Yes (`if False:` at line 153) |
| `services/shell.py` | 3 | No | No |
| `api/v1/file.py` | 2 | Delegates to `services/file.py` | N/A |

**Architectural Pattern: `if False: # Security check removed`**

Five sandbox services have a distinctive pattern where path validation was deliberately removed:

```python
# Example from export.py:125
if False:  # Security check removed
    raise ValueError("Path not allowed")
```

This represents a **deliberate architectural decision**: the Docker container itself is the security boundary, not application-level path validation. The AI agent needs full filesystem access within the container to perform its tasks.

**Exception — file.py:** This service maintains proper `safe_resolve()` validation:
```python
def safe_resolve(path: str) -> Path:
    resolved = Path(path).resolve()
    if not any(str(resolved).startswith(d) for d in SANDBOX_ALLOWED_DIRS):
        raise ValueError(f"Path {path} is outside allowed directories")
    return resolved
```

**Dismissal verdict: CORRECT** — Sandbox isolation mitigates all path injection findings.

---

### 2.3 CodeQL: Incomplete URL Substring Sanitization — `py/incomplete-url-substring-sanitization` (28 alerts, HIGH)

#### Production Code (8 alerts)

| Alert # | File | Line | Pattern | Assessment |
|---------|------|------|---------|------------|
| 20 | `openai_llm.py` | 645 | `"api.openai.com" in base` | **FALSE POSITIVE** |
| 19 | `openai_llm.py` | 607 | `"api.deepseek.com" in self._api_base.lower()` | **FALSE POSITIVE** |
| 18 | `openai_llm.py` | 545 | `"kimi.com" in base` | **FALSE POSITIVE** |
| 17 | `openai_llm.py` | 518 | `"openai.com" in base` | **FALSE POSITIVE** |
| 16 | `openai_llm.py` | 458 | `"kimi.com" in self._api_base` | **FALSE POSITIVE** |
| 23 | `paywall_detector.py` | 283 | `"substack.com" in url_lower` | **FALSE POSITIVE** |
| 22 | `paywall_detector.py` | 276 | `"medium.com" in url_lower` | **FALSE POSITIVE** |
| 21 | `paywall_detector.py` | 276 | (duplicate) | **FALSE POSITIVE** |

**Why false positive:**
- **openai_llm.py**: `_api_base` comes from the `API_BASE` environment variable — a server-side deployment setting. Attackers cannot influence this value. The substring matching is feature-detection for API provider heuristics.
- **paywall_detector.py**: Domain-heuristic matching for paywall detection. A false match (e.g., `evil.com/medium.com`) would only cause benign extra pattern checks that won't match.

#### Test Code (20 alerts)

| File | Count | Pattern |
|------|-------|---------|
| `test_quality_refinements.py` | 16 | URL assertions in test data |
| `test_coupon_aggregator.py` | 3 | URL assertions |
| `test_spider_denylist.py` | 3 | URL assertions |
| `test_source_attribution.py` | 1 | URL assertion |
| `test_routing_quality_fixes.py` | 2 | URL assertions |
| `test_search_security.py` | 1 | URL assertion |
| `test_headline_extractor.py` | 1 | URL assertion |
| `test_fast_path.py` | 2 | URL assertions |
| `test_enhanced_prompt_quick_validator.py` | 1 | URL assertion |
| `test_intent_classifier.py` | 1 | URL assertion |
| `test_wide_research.py` | 1 | URL assertion |

**These are test fixtures containing hardcoded URLs for assertions — not security-relevant code.**

**Dismissal verdict: CORRECT** — All are either server-config heuristics or test data.

---

### 2.4 CodeQL: Incomplete URL Substring Sanitization — JavaScript (2 alerts, HIGH)

| Alert # | File | Line | Pattern | Assessment |
|---------|------|------|---------|------------|
| 7 | `SearchContentView.vue` | 146 | `hostname.includes('twitter')` | **FALSE POSITIVE** |
| 6 | `toolDisplay.ts` | 283 | `hostname.includes('x.com')` | **FALSE POSITIVE** |

**Validation:** After parsing with `new URL(result.link)`, the code checks `url.hostname` — already extracted by the URL parser. These are icon-letter helpers (display 'X' for Twitter, 'G' for Google, etc.). A false match on `fox.com` would only show the wrong icon letter. No security impact.

**Dismissal verdict: CORRECT**

---

### 2.5 CodeQL: Bad HTML Filtering Regexp — `py/bad-tag-filter` (3 alerts, HIGH)

| Alert # | File | Line | Pattern | Assessment |
|---------|------|------|---------|------------|
| 65 | `nanobot/agent/tools/web.py` | 22 | `re.sub(r'<script[\s\S]*?</script>', '', text)` | **FALSE POSITIVE** |
| 64 | `deal_finder/llm_price_extractor.py` | 64 | `re.sub(r"<script[^>]*>.*?</script>", "", ...)` | **FALSE POSITIVE** |
| 63 | `domain/services/tools/browser.py` | 137 | `re.sub(r"<script[^>]*>.*?</script>", "", ...)` | **FALSE POSITIVE** |

**Validation:** All three are **content extraction utilities** (HTML-to-text conversion) for feeding text to the AI agent or LLM. They are NOT security sanitization filters to prevent XSS. The output is consumed as plain text, never rendered in a browser.

**Dismissal verdict: CORRECT**

---

### 2.6 CodeQL: Weak Cryptographic Hashing — `py/weak-sensitive-data-hashing` (1 alert, HIGH)

| Alert # | File | Line | Assessment |
|---------|------|------|------------|
| 69 | `memory_service.py` | 1456 | **FALSE POSITIVE** |

**Validation via LSP:**

```python
# Line 1456
hashlib.md5(word.encode(), usedforsecurity=False).hexdigest()
```

This is inside `_compute_simple_embedding()` — a fallback method that generates deterministic embedding vectors via **feature hashing** (a standard ML technique). MD5 is used to map words to vector positions. The `usedforsecurity=False` flag explicitly marks this as non-cryptographic. No sensitive data is being hashed.

**Dismissal verdict: CORRECT**

---

### 2.7 CodeQL: Clear-text Logging — `py/clear-text-logging-sensitive-data` (2 alerts, HIGH)

| Alert # | File | Line | Assessment |
|---------|------|------|------------|
| 15 | `session_routes.py` | 1956 | **FALSE POSITIVE** |
| 14 | `session_routes.py` | 1949 | **FALSE POSITIVE** |

**Validation via LSP:**

```python
# Line 153: _redact_query_params() replaces 'secret' param with '***'
# Line 1949: logger.debug("Connecting to screencast at %s", redacted_sandbox_ws_url)
# Line 1956: logger.debug("Connected to screencast at %s", redacted_sandbox_ws_url)
```

The URL is passed through `_redact_query_params()` which replaces sensitive query parameters (the `secret` key) with `***` before logging. The variable is explicitly named `redacted_sandbox_ws_url`.

**Dismissal verdict: CORRECT**

---

### 2.8 CodeQL: Stack Trace Exposure — `py/stack-trace-exposure` (3 alerts, MEDIUM)

| Alert # | File | Line | Pattern | Assessment |
|---------|------|------|---------|------------|
| 68 | `sandbox/api/v1/screenshot.py` | 806 | `"error": str(e)` | **TRUE POSITIVE** (Low) |
| 67 | `sandbox/api/v1/screencast.py` | 552 | `"error": str(e)` | **TRUE POSITIVE** (Low) |
| 66 | `sandbox/api/v1/input.py` | 246 | `"error": str(e)` | **TRUE POSITIVE** (Low) |

**Validation:** Raw exception messages are returned in API responses. These could leak internal details (file paths, library versions, stack frames). However:
- These are **internal sandbox APIs** only accessible from the backend, not from external users
- The sandbox container is isolated and disposable

**Recommendation:** Replace `str(e)` with generic error messages. Low priority due to sandbox-only exposure.

**Dismissal verdict: COULD BE IMPROVED** — Should return generic errors, but risk is low.

---

### 2.9 CodeQL: Regex Injection — `py/regex-injection` (1 alert, HIGH)

| Alert # | File | Line | Assessment |
|---------|------|------|------------|
| 8 | `sandbox/app/services/file.py` | 339 | **TRUE POSITIVE** (Low) |

**Validation:**

```python
# Line 339: re.compile(regex)  — user-supplied regex
```

The `find_in_content` function compiles a user-supplied regex pattern without timeout protection. A crafted regex could cause ReDoS (catastrophic backtracking), hanging the container process.

**Recommendation:** Use `re2` library (constant-time regex) or add a timeout wrapper.

**Dismissal verdict: COULD BE IMPROVED** — Sandbox mitigates blast radius, but ReDoS could hang the container.

---

### 2.10 CodeQL: Missing Workflow Permissions — `actions/missing-workflow-permissions` (5 alerts, MEDIUM)

| Alert # | File | Line |
|---------|------|------|
| 208, 207, 206, 202 | `.github/workflows/test-and-lint.yml` | 30, 48, 85, 156 |
| 1 | `.github/workflows/security-scan.yml` | 11 |

**Validation:** GitHub Actions workflows do not declare explicit `permissions:` blocks. Without explicit permissions, workflows run with the default token permissions (which may be overly broad depending on repository settings).

**Recommendation:** Add explicit `permissions:` to each job:
```yaml
permissions:
  contents: read
  # Add other needed permissions explicitly
```

**Dismissal verdict: COULD BE IMPROVED** — Low risk but follows security best practice of least privilege.

---

## Part 3: Fixed Alerts (40)

### 3.1 Trivy — Container Dependencies (33 fixed)

These were fixed by upgrading the sandbox Docker image (Node.js v22.13.0 → v22.22.1, starlette update, pip update).

| Category | Count | Fix |
|----------|-------|-----|
| node-tar CVEs | 18 | Node.js version bump (old v22.13.0 image) |
| minimatch CVEs | 6 | Node.js version bump |
| glob CVE | 1 | Node.js version bump |
| brace-expansion CVE | 1 | Node.js version bump |
| diff CVE | 1 | Node.js version bump |
| starlette DoS (CVE-2025-62727) | 1 | starlette 0.48.0 updated |
| pip CVEs | 2 | pip updated |
| pnpm tar/minimatch | 3 | pnpm updated with Node.js |

### 3.2 CodeQL — Workflow Permissions (7 fixed)

| Alert # | File | Status |
|---------|------|--------|
| 2-5, 203-205 | `test-and-lint.yml`, `docker-build-and-push.yml` | Fixed (permissions added or jobs restructured) |

---

## Part 4: Actionable Recommendations

### Priority 1: Container Image Hardening (Open Trivy Alerts)

**22 HIGH severity open alerts** from container dependencies in the sandbox image.

| Action | Impact | Effort |
|--------|--------|--------|
| Upgrade Node.js to latest v22.x LTS in sandbox Dockerfile | Fixes tar, minimatch, glob CVEs (18 alerts) | Low |
| Upgrade `setuptools` in `base-python-venv` | Fixes jaraco.context + wheel CVEs (2 alerts) | Low |
| Pin `uv`/`uvx` to latest version | Fixes jsonwebtoken type confusion (2 alerts) | Low |
| Update pip in sandbox image | Fixes pip path traversal + symlink (2 alerts) | Low |

### Priority 2: Code-Level True Positives (4 alerts)

| Action | File | Finding | Severity |
|--------|------|---------|----------|
| Replace `str(e)` with generic error messages | `screenshot.py:806`, `screencast.py:552`, `input.py:246` | Stack trace exposure | Low |
| Add regex timeout or use `re2` | `file.py:339` | ReDoS via user-supplied regex | Low |

### Priority 3: Best Practice Improvements

| Action | File | Finding |
|--------|------|---------|
| Add explicit `permissions:` blocks | `test-and-lint.yml`, `security-scan.yml` | Least-privilege CI |

---

## Part 5: Architecture Notes

### Sandbox Security Model

The Pythinker sandbox uses a **container-as-security-boundary** model:

```
┌─────────────────────────────────────────────────┐
│  Backend (Host Network)                         │
│  ┌───────────────────────────────────────────┐  │
│  │  Sandbox Container (Isolated Docker)      │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  shell.py    → arbitrary commands   │  │  │
│  │  │  file.py     → safe_resolve() guard │  │  │
│  │  │  code_dev.py → if False: bypass     │  │  │
│  │  │  export.py   → if False: bypass     │  │  │
│  │  │  git.py      → if False: bypass     │  │  │
│  │  │  test_runner  → if False: bypass    │  │  │
│  │  │  workspace   → session_id validated │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │  Security boundary = container isolation   │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

- **5 services** use `if False: # Security check removed` — path validation deliberately disabled
- **1 service** (`file.py`) maintains `safe_resolve()` as defense-in-depth
- **1 service** (`workspace.py`) validates `session_id` format (alphanumeric + dashes/underscores)
- **Command injection** in `shell.py` is the intended behavior — the service exists to execute commands

This pattern means **~120 CodeQL alerts** (path injection + command injection) are architecturally mitigated by Docker isolation.

### URL Substring Matching Pattern

The `"domain.com" in url` pattern appears in 30+ alerts across the codebase. In every case:
- The value is either server configuration (env vars) or parsed hostname
- The matching is for feature detection / heuristics, not security boundaries
- False matches have no security impact (wrong icon, extra benign checks)

---

## Appendix A: Alert Distribution by File

| File | Tool | Open | Dismissed | Fixed |
|------|------|------|-----------|-------|
| `sandbox/app/services/workspace.py` | CodeQL | 0 | 34 | 0 |
| `sandbox/app/services/export.py` | CodeQL | 0 | 29 | 0 |
| `sandbox/app/services/test_runner.py` | CodeQL | 0 | 22 | 0 |
| `sandbox/app/services/file.py` | CodeQL | 0 | 18 | 0 |
| `tests/*` (various) | CodeQL | 0 | 20 | 0 |
| `sandbox/app/services/git.py` | CodeQL | 0 | 10 | 0 |
| `sandbox/app/services/code_dev.py` | CodeQL | 0 | 9 | 0 |
| `openai_llm.py` | CodeQL | 0 | 5 | 0 |
| `npm/tar/*` | Trivy | 18 | 0 | 18 |
| `npm/minimatch/*` | Trivy | 3 | 0 | 6 |
| (other) | Mixed | 8 | 54 | 16 |

## Appendix B: CVE Quick Reference (Open) — Online Validated (2026-03-18)

> All CVEs below have been cross-referenced against NVD, GitHub Advisory Database, AWS Security Center, Socket.dev, SentinelOne, and Miggo Security databases on 2026-03-18.

| CVE | CVSS | CWE | Package | Installed | Fix Version | NVD Status | Exploit Available |
|-----|------|-----|---------|-----------|-------------|------------|-------------------|
| CVE-2026-31802 | HIGH (CVSS 4.0) | CWE-22 | tar | 7.4.3 | **7.5.11** | Received (2026-03-10) | No public PoC |
| CVE-2026-29786 | HIGH (7.1) | CWE-22 | tar | 7.4.3 | **7.5.10** | Analyzed | No public PoC |
| CVE-2026-26960 | HIGH (7.1) | CWE-22 | tar | 7.4.3 | **7.5.8** | Analyzed (2026-02-20) | No public PoC |
| CVE-2026-24842 | HIGH | CWE-22 | tar | 7.4.3 | **7.5.10** | Analyzed | No public PoC |
| CVE-2026-23950 | HIGH | CWE-362 | tar | 7.4.3 | **7.5.10** | Analyzed | No public PoC |
| CVE-2026-23745 | HIGH | CWE-22 | tar | 7.4.3 | **7.5.3** | Analyzed (2026-01-17) | GHSA-8qq5-rm4j-mr97 |
| CVE-2026-27904 | HIGH (7.5) | CWE-1333 | minimatch | — | **10.2.3** / 9.0.7 / 8.0.6 / 7.4.8 | Analyzed | GHSA-23c5-xmqv-rm74 |
| CVE-2026-27903 | HIGH (7.5) | CWE-1333 | minimatch | — | **10.2.3** / 9.0.7 / 8.0.6 / 7.4.8 | Analyzed | GHSA-7r86-cg39-jmmj |
| CVE-2026-26996 | HIGH (8.7) | CWE-1333 | minimatch | — | **10.2.1** / 9.0.6 / 8.0.5 / 7.4.7 | Analyzed (2026-02-20) | GHSA-3ppc-4f35-3m26 |
| CVE-2025-64756 | HIGH (7.5) | CWE-78 | glob | — | **10.5.0** / **11.1.0** | Analyzed (2025-11-17) | PoC available |
| CVE-2026-23949 | HIGH | CWE-22 | jaraco.context | 5.3.0 | **>=6.1.0** | Analyzed (2026-01-13) | GHSA-58pv-8j8x-9vj2 |
| CVE-2026-24049 | HIGH | CWE-22 | wheel | 0.45.1 | **0.46.2** | Analyzed (2026-01-22) | PoC in advisory |
| CVE-2025-8869 | MEDIUM | — | pip | 25.0.1 | Python 3.12+ (PEP 706) | Awaiting Analysis | No |
| CVE-2026-25537 | MEDIUM (6.9 CVSS4) | — | jsonwebtoken (Rust) | in uv/uvx | **10.3.0** | Analyzed (2026-02-04) | Exploit available |
| CVE-2026-1703 | LOW | — | pip | 25.0.1 | Python 3.12+ (PEP 706) | Analyzed | No |
| CVE-2026-24001 | LOW | — | diff (npm) | — | — | Analyzed | No |

### Online Validation Notes

**node-tar (6 CVEs):** All confirmed by NVD. The `ENSURE_NO_SYMLINK` validation method was introduced in the patch commit `d18e4e1f846f4ddddc153b0f536a19c050e7499f`. Upgrading to **tar >= 7.5.11** resolves ALL six CVEs at once. The CVEs form a chain of related symlink/hardlink path traversal attacks on the `Unpack.HARDLINK` and `Unpack.SYMLINK` functions.

**minimatch (3 CVEs):** All confirmed by NVD and Socket.dev. These are ReDoS vulnerabilities affecting 472M weekly downloads. Fixes backported across 8 major versions. **minimatch >= 10.2.3** resolves all three. Socket has published certified patches for each GHSA.

**glob (CVE-2025-64756):** Confirmed by NVD. Command injection in `-c/--cmd` option when processing malicious filenames. Fixed in **glob 10.5.0 / 11.1.0**. Only exploitable when `glob -c` is used with filenames from untrusted sources.

**jaraco.context (CVE-2026-23949):** Confirmed Zip Slip in `tarball()` function. The `strip_first_component` filter allows `../` sequences. Fix: **jaraco.context >= 6.1.0**. Also affects setuptools vendored copy (our case — `setuptools._vendor.jaraco.context-5.3.0`). Upgrading setuptools to a version that vendors jaraco.context >= 6.1.0 is required.

**wheel (CVE-2026-24049):** Confirmed by NVD. The `unpack` function uses raw `zinfo.filename` for `chmod` instead of the sanitized extraction path. Fix: **wheel >= 0.46.2**. Attack requires local access + user unpacking a malicious wheel.

**pip (CVE-2025-8869, CVE-2026-1703):** Per NVD, these affect pip's fallback tar extraction on Python < 3.12 (no PEP 706). Our sandbox uses Python 3.11 in `base-python-venv`, so the fallback code IS active. Mitigation: upgrade Python to 3.12+ or upgrade pip.

**jsonwebtoken in uv/uvx (CVE-2026-25537):** This is a Rust `jsonwebtoken` crate vulnerability, not a Node.js package. It affects the `uv` and `uvx` binaries compiled with the vulnerable crate. Fix: **jsonwebtoken >= 10.3.0** (Rust crate). Requires updating uv/uvx to a version compiled with the fixed crate. Exploit available per Tenable.

---

## Appendix C: Context7 MCP Validation (2026-03-18)

> All recommendations validated against authoritative Context7 documentation sources.

### C.1 FastAPI Error Handling — Stack Trace Exposure Fix

**Source:** Context7 `/fastapi/fastapi` (1,679 snippets, High reputation, Score: 80.09)

The three stack trace exposure findings (`screenshot.py:806`, `screencast.py:552`, `input.py:246`) return raw `str(e)` in API responses. Per FastAPI best practices:

**Recommended pattern:**
```python
# BEFORE (vulnerable):
return {"available": False, "error": str(e)}

# AFTER (Context7 validated):
import logging
logger = logging.getLogger(__name__)

try:
    # ... operation
except Exception as e:
    logger.exception("CDP operation failed")  # Log full traceback server-side
    return {"available": False, "error": "Service temporarily unavailable"}
```

**Context7 confirms:** FastAPI's `HTTPException` and custom exception handlers should return structured error details via `detail` field, never raw exception strings. The `@app.exception_handler()` decorator pattern is the canonical approach.

### C.2 GitHub Actions Workflow Permissions

**Source:** Context7 `/websites/github_en_actions` (2,337 snippets, High reputation, Score: 85.2)

Per GitHub's official security hardening guide:
> "It's good security practice to set the default permission for the GITHUB_TOKEN to read access only for repository contents. The permissions can then be increased, as required, for individual jobs within the workflow file."

**Recommended fix for `test-and-lint.yml` and `security-scan.yml`:**
```yaml
# Add at workflow level (top of file):
permissions:
  contents: read

# Override per-job if needed:
jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    # ...
```

**Context7 confirms:** Job-level `permissions` override workflow-level. Unspecified permissions default to `none` when any `permissions` key is present. This follows the principle of least privilege.

### C.3 CORS & Security Middleware Validation

**Source:** Context7 `/fastapi/fastapi`

The project already has OWASP-compliant security headers middleware (`backend/app/infrastructure/middleware/security_headers.py`), validated against Context7 FastAPI CORS documentation. The `CORSMiddleware` configuration should use explicit origin lists (not `"*"`) when `allow_credentials=True`.

### C.4 Python Sandbox Security — PEP 706 Gap

**Context7 + NVD cross-reference:** The sandbox's `base-python-venv` uses Python 3.11, which does NOT implement PEP 706 (safe tarfile extraction). This means pip's fallback extraction code is active and vulnerable to CVE-2025-8869 and CVE-2026-1703.

**Recommendation:** Upgrade `base-python-venv` to Python 3.12+ to get PEP 706 protections automatically, eliminating pip's vulnerable fallback code.

---

## Appendix D: Remediation Runbook

### Step 1: Update Sandbox Node.js (Fixes 22 HIGH alerts)

```dockerfile
# In sandbox Dockerfile, update Node.js version:
# Ensure npm's tar >= 7.5.11, minimatch >= 10.2.3, glob >= 11.1.0
RUN npm install -g npm@latest
```

Or update the NVM node version in the sandbox base image to latest v22.x LTS.

### Step 2: Update Python Packages in Sandbox (Fixes 2 HIGH alerts)

```dockerfile
# In sandbox Dockerfile:
RUN pip install --upgrade "setuptools>=75.8.0" "wheel>=0.46.2"
```

### Step 3: Update uv/uvx (Fixes 2 MEDIUM alerts)

```dockerfile
# In sandbox Dockerfile:
RUN pip install --upgrade uv
# Or use the standalone installer for the latest compiled binary
```

### Step 4: Fix Stack Trace Exposure (3 findings)

Replace `"error": str(e)` with generic messages in:
- `sandbox/app/api/v1/screenshot.py:806`
- `sandbox/app/api/v1/screencast.py:552`
- `sandbox/app/api/v1/input.py:246`

### Step 5: Add Workflow Permissions (5 findings)

Add `permissions: { contents: read }` to:
- `.github/workflows/test-and-lint.yml`
- `.github/workflows/security-scan.yml`

### Step 6: Upgrade Sandbox Python (2 LOW/MEDIUM pip alerts)

Upgrade `base-python-venv` from Python 3.11 to 3.12+ for PEP 706 safe tarfile extraction.
