# Agent Sandbox Threat Model

**Date:** 2026-02-13  
**Context:** Pythinker agent robustness and Docker sandbox hardening  
**Reference:** `docs/plans/2026-02-13-agent-robustness-docker-sandbox-hardening-plan.md`

---

## Scope

This threat model addresses security risks for the Pythinker AI agent system, where:

- An LLM-driven agent executes tools (browser, terminal, files, search) inside Docker sandbox containers
- Sandboxes may be static (compose-managed) or dynamic (Docker API–created)
- The backend orchestrates sessions, invokes sandboxes, and streams events to the frontend

---

## Threat Paths

### 1. Prompt-to-Shell Escape Attempts

**Description:** Malicious or compromised prompts attempt to bypass guardrails and execute arbitrary shell commands with elevated impact.

**Attack vectors:**
- Prompt injection to run `rm -rf /`, `curl | bash`, or similar destructive commands
- Exploitation of agent tool routing to invoke shell tool with attacker-controlled arguments
- Abuse of file tool to write malicious scripts and execute them via terminal
- Social engineering the agent to bypass security critic checks via misleading context

**Mitigations:**
- Security critic as mandatory gate before execution (Task 7): blocks CRITICAL/HIGH risk patterns
- Guardrails on input/output (guardrails.py): injection, jailbreak, sensitive data detection
- Capability restrictions in container: `cap_drop: ALL`, selective `cap_add`
- Seccomp profile blocking dangerous syscalls (mount, reboot, kexec_load, init_module)
- No root execution in container: `USER ubuntu`, no `NOPASSWD:ALL`

**Residual risk:** Medium. Sophisticated polymorphic payloads may evade pattern-based detection; LLM-based semantic analysis in security critic provides defense-in-depth.

---

### 2. Sandbox-to-Host Breakout Vectors

**Description:** Code running inside the sandbox attempts to escape confinement and access or affect the host or other containers.

**Attack vectors:**
- Exploitation of kernel vulnerabilities via syscalls
- Abuse of Docker socket mount (`/var/run/docker.sock`) from backend to create privileged containers
- Namespace escape via `unshare`, `nsenter`, or `/proc/*/ns/*` manipulation
- Privilege escalation via `setuid` binaries, `chmod +s`, or container escape exploits

**Mitigations:**
- `no-new-privileges:true`: prevents privilege escalation via setuid/setgid
- `cap_drop: ALL` with minimal `cap_add`: reduces privilege surface
- Custom seccomp profile: blocks namespace manipulation, module loading, mount
- Docker socket mounted read-only (`:ro`) on backend; sandbox never gets Docker socket
- Non-root container: limits impact of breakout attempts

**Residual risk:** Low. Defense-in-depth via seccomp, capabilities, and no-new-privileges. Dynamic sandbox creation uses policy contract (Task 2) for equivalent hardening.

---

### 3. Cross-Session Data Bleed

**Description:** Data from one user session leaks into another session or into shared storage.

**Attack vectors:**
- Shared volume or tmpfs between sandboxes without proper isolation
- Browser profile or cache reuse across sessions
- Memory or process visibility across container boundaries
- Agent memory/context contamination from previous sessions

**Mitigations:**
- Per-session sandbox lifecycle (static pool or dynamic per-session)
- tmpfs for `/home/ubuntu/.cache` with uid/gid and mode; cleared on container recreation
- Session locking in agent_domain_service prevents concurrent modifications
- MongoDB session events scoped by session_id; Redis keys namespaced

**Residual risk:** Low. Session isolation enforced by design; pool TTL and eviction limit exposure window.

---

### 4. Resource Exhaustion and Denial-of-Service Loops

**Description:** Agent behavior or malicious input causes resource exhaustion, degrading or halting the system.

**Attack vectors:**
- Infinite loops in agent planning or execution
- Memory exhaustion: OOM kills, cascading restarts
- PID exhaustion: fork bombs, runaway subprocesses
- CPU saturation: mining, tight loops
- Storage exhaustion: unbounded log or artifact writes

**Mitigations:**
- Resource limits in compose: `memory: 3G`, `cpus: 1.5`, `pids: 300`
- Circuit breaker in sandbox pool: 5 failures, exponential backoff (max 300s)
- Orphan reaper and TTL eviction in sandbox pool
- Docker events monitoring for OOM kills
- Timeouts on browser warmup (20s with backoff), agent steps, tool execution
- tmpfs for /tmp, /run, .cache limits disk impact

**Residual risk:** Medium. Limits cap blast radius but cannot prevent all DoS; monitoring and alerting (Task 9) improve detection.

---

## Chrome `--no-sandbox` Rationale

Chrome is launched with `--no-sandbox` and `--disable-setuid-sandbox`. This is **architecturally correct** when:

1. The container provides equivalent isolation via:
   - `cap_drop: ALL` + selective `cap_add`
   - Custom seccomp profile
   - `no-new-privileges:true`
2. Chrome's inner sandbox relies on `clone()`, `setuid`, and PID namespaces that conflict with container-level restrictions.
3. Delegating sandboxing to the container avoids redundancy and compatibility issues.

**Documentation requirement:** The rationale must be documented in the hardening baseline and security policy so it is not mistaken for a security gap.

---

## Out-of-Scope (Deferred)

- Host-level rootless Docker or userns-remap (Task 8 adds playbook, not enforcement)
- Supply chain attacks on base images or dependencies
- LLM provider security (API key handling, prompt leakage to provider)
