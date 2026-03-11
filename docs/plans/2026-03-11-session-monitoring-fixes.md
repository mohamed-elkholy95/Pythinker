# Session Monitoring Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 7 bugs identified during live session monitoring of session `e06d751bb19648f3` — evidence enforcement, security bypass, prompt correctness, hallucination gating, budget phase mapping, timeout profiles, and sandbox ownership.

**Architecture:** All fixes target existing enforcement points in the runtime loop. No new services or abstractions. Changes touch `execution.py` (step-level evidence gate, hallucination downgrade), `plan_act.py` (security bypass, retry injection, budget phase), `prompts/execution.py` (phantom citations), `openai_llm.py` + `config_llm.py` (timeout profiles), `docker_sandbox.py` + `agent_service.py` (sandbox ownership).

**Tech Stack:** Python 3.12, FastAPI, pytest, Pydantic v2, Redis, asyncio

**Design Document:** `docs/plans/2026-03-11-session-monitoring-fixes-design.md`

---

## Task 1: Step-Level External Evidence Enforcement (Fix 4A — P0)

Research steps must acquire external evidence via search/browser tools. Steps that complete without calling any evidence-producing tool are marked FAILED and retried with a corrective system message.

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:490,559-682`
- Test: `backend/tests/unit/agents/test_execution_evidence_gate.py`

### Step 1: Write the failing tests

```python
# backend/tests/unit/agents/test_execution_evidence_gate.py
"""Tests for step-level external evidence enforcement (Fix 4A)."""

from app.domain.services.agents.execution import ExecutionAgent


class TestIsResearchStep:
    """Test research step detection by keyword matching."""

    def _make_checker(self):
        return type(
            "MockAgent",
            (),
            {
                "_RESEARCH_STEP_KEYWORDS": ExecutionAgent._RESEARCH_STEP_KEYWORDS,
                "_is_research_step": ExecutionAgent._is_research_step,
            },
        )()

    def test_research_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Research GLM-5 best practices")

    def test_investigate_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Investigate pricing models for cloud providers")

    def test_compare_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Compare React vs Vue performance benchmarks")

    def test_find_information_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Find information about Python 3.12 features")

    def test_gather_data_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Gather data on GPU benchmark results")

    def test_best_practices_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Document best practices for Docker security")

    def test_non_research_step_not_detected(self):
        agent = self._make_checker()
        assert not agent._is_research_step("Write the final report")
        assert not agent._is_research_step("Create a benchmark script")
        assert not agent._is_research_step("Generate a summary of findings")

    def test_case_insensitive(self):
        agent = self._make_checker()
        assert agent._is_research_step("RESEARCH the latest AI trends")


class TestExternalEvidenceTools:
    """Verify the evidence-producing tool set matches source_tracker.py dispatch."""

    def test_evidence_tools_match_source_tracker(self):
        from app.domain.models.tool_name import ToolName

        expected = {
            ToolName.INFO_SEARCH_WEB,
            ToolName.WIDE_RESEARCH,
            ToolName.BROWSER_NAVIGATE,
            ToolName.BROWSER_GET_CONTENT,
            ToolName.BROWSER_VIEW,
        }
        assert ExecutionAgent._EXTERNAL_EVIDENCE_TOOLS == expected
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_evidence_gate.py -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `_RESEARCH_STEP_KEYWORDS`, `_is_research_step`, and `_EXTERNAL_EVIDENCE_TOOLS` do not exist on `ExecutionAgent`.

### Step 3: Implement keywords, detection method, and evidence tool set

In `backend/app/domain/services/agents/execution.py`, add class-level constants and method to `ExecutionAgent`. Find the existing `_SYNTHESIS_KEYWORDS` class variable and add after it:

```python
# ── Research step detection (Fix 4A) ─────────────────────────
_RESEARCH_STEP_KEYWORDS: ClassVar[tuple[str, ...]] = (
    "research",
    "investigate",
    "compare",
    "pricing",
    "best practices",
    "find information",
    "gather data",
)

_EXTERNAL_EVIDENCE_TOOLS: ClassVar[frozenset] = frozenset({
    ToolName.INFO_SEARCH_WEB,
    ToolName.WIDE_RESEARCH,
    ToolName.BROWSER_NAVIGATE,
    ToolName.BROWSER_GET_CONTENT,
    ToolName.BROWSER_VIEW,
})
```

Add the method (near `_is_synthesis_step`):

```python
def _is_research_step(self, step_description: str) -> bool:
    """Detect if a step is a research step by keyword matching."""
    desc_lower = step_description.lower()
    return any(kw in desc_lower for kw in self._RESEARCH_STEP_KEYWORDS)
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_evidence_gate.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all 10 tests)

### Step 5: Add the evidence flag to execute_step tool-event loop

In `execution.py`, in `execute_step()`, at line ~490 (after `_step_tool_errors = 0`), add:

```python
_saw_external_evidence = False
```

In the tool-event loop at line ~574 (after `self._track_sources_from_tool_event(event)`), add:

```python
# Fix 4A: Track external evidence acquisition
if event.function_result and event.function_result.success:
    if func_name in self._EXTERNAL_EVIDENCE_TOOLS:
        _saw_external_evidence = True
```

### Step 6: Add the evidence gate at step completion

At line ~670 (after `step.status = ExecutionStatus.COMPLETED` / `step.success = True`), add the evidence gate:

```python
# Fix 4A: Research steps must acquire external evidence
if (
    step.status == ExecutionStatus.COMPLETED
    and not _saw_external_evidence
    and self._is_research_step(step.description or "")
):
    step.status = ExecutionStatus.FAILED
    step.success = False
    step.error = "Research step completed without external evidence"
    logger.warning(
        "Step %s failed evidence gate: research step with no search/browser tool calls",
        step.id,
    )
```

### Step 7: Run full test suite for execution

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/ tests/domain/services/agents/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS

### Step 8: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/agents/execution.py backend/tests/unit/agents/test_execution_evidence_gate.py
git commit -m "feat(agents): add step-level external evidence enforcement for research steps

Research steps that complete without calling any search/browser tool
are now marked FAILED. Uses keyword detection (_is_research_step) and
a step-local _saw_external_evidence flag set during the tool-event loop.
Mirrors source_tracker.py tool dispatch set exactly."
```

---

## Task 2: Evidence Retry Injection in PlanActFlow (Fix 4A continued — P0)

When a research step fails with "external evidence" error, inject a corrective system message on retry telling the LLM to use search/browser tools.

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:3229-3243`
- Test: `backend/tests/domain/services/flows/test_plan_act_evidence_retry.py`

### Step 1: Write the failing test

```python
# backend/tests/domain/services/flows/test_plan_act_evidence_retry.py
"""Tests for evidence retry injection in PlanActFlow step loop (Fix 4A)."""


def test_evidence_retry_message_text():
    """Verify the corrective message content for evidence-gated retries."""
    from app.domain.services.flows.plan_act import _EVIDENCE_RETRY_SYSTEM_MESSAGE

    assert "info_search_web" in _EVIDENCE_RETRY_SYSTEM_MESSAGE
    assert "wide_research" in _EVIDENCE_RETRY_SYSTEM_MESSAGE
    assert "browser_navigate" in _EVIDENCE_RETRY_SYSTEM_MESSAGE
    assert "training data" in _EVIDENCE_RETRY_SYSTEM_MESSAGE


def test_should_inject_evidence_retry_message():
    """When step.error contains 'external evidence', retry should inject message."""
    from app.domain.services.flows.plan_act import _should_inject_evidence_retry

    assert _should_inject_evidence_retry(
        attempt=1, step_error="Research step completed without external evidence"
    )


def test_should_not_inject_on_first_attempt():
    """First attempt (attempt=0) should never inject evidence retry."""
    from app.domain.services.flows.plan_act import _should_inject_evidence_retry

    assert not _should_inject_evidence_retry(
        attempt=0, step_error="Research step completed without external evidence"
    )


def test_should_not_inject_for_other_errors():
    """Non-evidence errors should not trigger injection."""
    from app.domain.services.flows.plan_act import _should_inject_evidence_retry

    assert not _should_inject_evidence_retry(
        attempt=1, step_error="Tool execution failed"
    )
    assert not _should_inject_evidence_retry(
        attempt=1, step_error=None
    )
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_evidence_retry.py -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `_EVIDENCE_RETRY_SYSTEM_MESSAGE` and `_should_inject_evidence_retry` don't exist.

### Step 3: Implement the retry injection

In `backend/app/domain/services/flows/plan_act.py`, add module-level constants (near top, after imports):

```python
_EVIDENCE_RETRY_SYSTEM_MESSAGE: str = (
    "Your previous attempt completed without using search or browsing tools. "
    "You MUST use info_search_web, wide_research, or browser_navigate to gather "
    "real data from the internet. Do not rely on training data alone."
)


def _should_inject_evidence_retry(attempt: int, step_error: str | None) -> bool:
    """Return True if this retry should inject an evidence-corrective system message."""
    if attempt < 1 or not step_error:
        return False
    return "external evidence" in step_error
```

In the step retry loop (~line 3229-3243), after `step.result = None` (line 3242) and before `step.status = ExecutionStatus.RUNNING` (line 3246), add:

```python
# Fix 4A: Inject corrective system message for evidence-gated retries
if _should_inject_evidence_retry(attempt, step.error):
    logger.info("Injecting evidence retry message for step %s (attempt %d)", step.id, attempt)
    step_executor.system_prompt = (
        (step_executor.system_prompt or "") + "\n\n" + _EVIDENCE_RETRY_SYSTEM_MESSAGE
    )
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_evidence_retry.py -v --no-header -p no:cov -o addopts=`

Expected: PASS

### Step 5: Run broader plan_act tests

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS (no regressions)

### Step 6: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_evidence_retry.py
git commit -m "feat(flows): inject corrective system message on evidence-gated retries

When a research step fails the external evidence gate and is retried,
PlanActFlow now injects a system message telling the LLM to use
search/browser tools instead of relying on training data."
```

---

## Task 3: Synthesis Gate Backstop (Fix 4B — P0)

Add a secondary check in `_check_synthesis_gate()`: if no sources exist AND no evidence records exist, return hard_fail.

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:298-323`
- Test: `backend/tests/unit/agents/test_execution_synthesis_gate.py` (extend existing)

### Step 1: Write the failing test

Append to `backend/tests/unit/agents/test_execution_synthesis_gate.py`:

```python
class TestSynthesisGateBackstop:
    """Test the backstop: no sources + no evidence = hard_fail (Fix 4B)."""

    def test_backstop_hard_fail_no_sources_no_evidence(self):
        """When source_tracker has no sources AND policy has no evidence_records, hard_fail."""
        from unittest.mock import MagicMock, patch

        from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = []
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = []
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
        )

        with patch("app.domain.services.agents.execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result is not None
        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("No external evidence" in r for r in result.reasons)

    def test_backstop_passes_with_sources(self):
        """When source_tracker has sources, backstop does not fire."""
        from unittest.mock import MagicMock, patch

        from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = [MagicMock()]
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = []
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
        )

        with patch("app.domain.services.agents.execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result.verdict == SynthesisGateVerdict.pass_

    def test_backstop_passes_with_evidence_records(self):
        """When policy has evidence_records, backstop does not fire."""
        from unittest.mock import MagicMock, patch

        from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = []
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = [MagicMock()]
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
        )

        with patch("app.domain.services.agents.execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result.verdict == SynthesisGateVerdict.pass_
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_synthesis_gate.py::TestSynthesisGateBackstop -v --no-header -p no:cov -o addopts=`

Expected: FAIL — backstop logic not implemented.

### Step 3: Implement the backstop

In `execution.py:_check_synthesis_gate()`, after `return result` on line 323 but before the method ends, add the backstop. Replace the existing method body (lines 298-323) to insert the backstop between the shadow-mode check and the return:

After the existing `return None  # Don't block in shadow mode` (line 321) and before `return result` (line 323), add:

```python
# Fix 4B: Backstop — if policy passed but no evidence at all, override to hard_fail
if result.verdict != SynthesisGateVerdict.hard_fail:
    has_sources = bool(self._source_tracker.get_collected_sources())
    has_evidence = bool(
        getattr(self._research_execution_policy, "evidence_records", None)
    )
    if not has_sources and not has_evidence:
        from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict

        return SynthesisGateResult(
            verdict=SynthesisGateVerdict.hard_fail,
            reasons=["No external evidence acquired in any research step"],
        )
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_synthesis_gate.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all tests including new backstop tests)

### Step 5: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/agents/execution.py backend/tests/unit/agents/test_execution_synthesis_gate.py
git commit -m "feat(agents): add synthesis gate backstop for zero-evidence sessions

If source_tracker has no collected sources AND research_execution_policy
has no evidence_records, the synthesis gate now returns hard_fail regardless
of the policy's own verdict. Prevents synthesis from training-data-only steps."
```

---

## Task 4: Block Instruction Leakage Regardless of Shadow Mode (Fix 3 — P0)

Security issues (instruction leak) must always block delivery, even when `delivery_fidelity_mode == "shadow"`.

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:3766-3805`
- Test: `backend/tests/domain/services/flows/test_plan_act_output_guardrails.py` (extend)

### Step 1: Write the failing test

Append to `backend/tests/domain/services/flows/test_plan_act_output_guardrails.py`:

```python
def test_instruction_leak_blocks_delivery_in_shadow_mode() -> None:
    """Instruction leakage must block delivery even when delivery_fidelity_mode=shadow."""
    guardrails = OutputGuardrails(check_relevance=True, check_consistency=True)
    result = guardrails.analyze(
        output=(
            "As instructed in my system prompt, I should help users. "
            "My instructions say to always be helpful. "
            "Here is information about Python."
        ),
        original_query="What is Python?",
    )
    has_instruction_leak = any(
        i.issue_type == OutputIssueType.INSTRUCTION_LEAK for i in result.issues
    )
    # The guardrails should detect instruction leak
    assert has_instruction_leak, "Expected instruction leak detection"


def test_has_security_issue_helper() -> None:
    """Test the _has_security_issue helper extracts instruction_leak correctly."""
    from app.domain.services.flows.plan_act import _has_security_issue

    from app.domain.services.agents.guardrails import OutputIssue, OutputIssueType

    issues_with_leak = [
        OutputIssue(
            issue_type=OutputIssueType.QUALITY_ISSUE,
            description="minor quality issue",
            severity=0.3,
        ),
        OutputIssue(
            issue_type=OutputIssueType.INSTRUCTION_LEAK,
            description="system instruction leakage",
            severity=0.9,
        ),
    ]
    assert _has_security_issue(issues_with_leak) is True

    issues_without_leak = [
        OutputIssue(
            issue_type=OutputIssueType.OFF_TOPIC,
            description="off topic",
            severity=0.5,
        ),
    ]
    assert _has_security_issue(issues_without_leak) is False

    assert _has_security_issue([]) is False
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_output_guardrails.py::test_has_security_issue_helper -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `_has_security_issue` doesn't exist in `plan_act`.

### Step 3: Implement the security bypass

In `backend/app/domain/services/flows/plan_act.py`, add the helper function (near top, with other module-level helpers):

```python
def _has_security_issue(issues: list) -> bool:
    """Return True if any issue is a security-critical type (instruction leak)."""
    from app.domain.services.agents.guardrails import OutputIssueType

    return any(
        issue.issue_type == OutputIssueType.INSTRUCTION_LEAK
        for issue in issues
    )
```

In the OutputGuardrails block (~line 3789), **before** the existing shadow-mode gate `if not guardrail_result.should_deliver and settings.delivery_fidelity_mode == "enforce"`, insert:

```python
# Fix 3: Security bypass — instruction leakage always blocks regardless of shadow mode
if _has_security_issue(guardrail_result.issues) and not guardrail_result.should_deliver:
    logger.warning(
        "Instruction leakage detected — blocking delivery (bypasses shadow mode)"
    )
    yield ErrorEvent(
        error="Output blocked: potential system instruction leakage detected"
    )
    self._transition_to(
        AgentStatus.ERROR,
        force=True,
        reason="instruction leakage blocked",
    )
    break
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_output_guardrails.py -v --no-header -p no:cov -o addopts=`

Expected: PASS

### Step 5: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_output_guardrails.py
git commit -m "fix(security): block instruction leakage regardless of shadow mode

OutputGuardrails instruction_leak issues now always block delivery,
even when delivery_fidelity_mode is 'shadow'. Shadow mode was designed
for quality heuristics — security issues should never be shadow-gated."
```

---

## Task 5: Remove Phantom Citation Scaffolding (Fix 2 — P0)

Remove fake `[1]`/`[2]` placeholders from the summarize prompt when `has_sources=False`.

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py:1435-1437`
- Test: `backend/tests/domain/services/prompts/test_phantom_citations.py`

### Step 1: Write the failing test

```python
# backend/tests/domain/services/prompts/test_phantom_citations.py
"""Tests for phantom citation removal when has_sources=False (Fix 2)."""

import re


def test_no_source_prompt_has_no_numbered_citations():
    """When has_sources=False, the prompt must not contain [1] or [2] markers."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        user_query="What is Python?",
        step_results=["Python is a programming language."],
        has_sources=False,
    )
    # Must NOT contain [N] citation markers
    numbered_refs = re.findall(r'\[\d+\]', prompt)
    # Filter out any that are inside legitimate markdown (like [1] in a list)
    # The specific pattern is "[1] Source Name - URL"
    assert "[1] Source Name - URL" not in prompt
    assert "[2] Source Name - URL" not in prompt


def test_no_source_prompt_has_no_reference_section():
    """When has_sources=False, no MANDATORY References header should appear."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        user_query="What is Python?",
        step_results=["Python is a programming language."],
        has_sources=False,
    )
    assert "Do NOT include a References section" in prompt or "No external sources" in prompt


def test_has_sources_prompt_keeps_references():
    """When has_sources=True, the References section should remain."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        user_query="What is Python?",
        step_results=["Python is a programming language."],
        has_sources=True,
    )
    assert "References" in prompt
    assert "List ALL cited sources" in prompt
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/prompts/test_phantom_citations.py -v --no-header -p no:cov -o addopts=`

Expected: First two tests FAIL — prompt still contains `[1] Source Name - URL`.

### Step 3: Implement the fix

In `backend/app/domain/services/prompts/execution.py`, replace lines 1435-1437:

**Old (lines 1435-1437):**
```python
## References (MANDATORY — NON-NEGOTIABLE)
{"List ALL cited sources with their numbers matching the inline citations. Every [N] citation" + chr(10) + "in the report MUST have a corresponding entry here." if has_sources else "[1] Source Name - URL" + chr(10) + "[2] Source Name - URL" + chr(10) + "(List ALL sources cited in the report.)"}
This section MUST be present and complete.""")
```

**New:**
```python
{_build_references_section(has_sources)}""")
```

Add a helper function earlier in the file (before `build_summarize_prompt`):

```python
def _build_references_section(has_sources: bool) -> str:
    """Build the references section based on source availability."""
    if has_sources:
        return (
            "## References (MANDATORY — NON-NEGOTIABLE)\n"
            "List ALL cited sources with their numbers matching the inline citations. "
            "Every [N] citation\nin the report MUST have a corresponding entry here.\n"
            "This section MUST be present and complete."
        )
    return (
        "No external sources were used. Do NOT include a References section or "
        "numbered citations like [1], [2]. Use inline attribution only."
    )
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/prompts/test_phantom_citations.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all 3 tests)

### Step 5: Run existing prompt tests

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/prompts/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS (no regressions)

### Step 6: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/prompts/execution.py backend/tests/domain/services/prompts/test_phantom_citations.py
git commit -m "fix(prompts): remove phantom citation scaffolding when no sources exist

The has_sources=False branch at line 1435 hardcoded fake [1]/[2]
placeholders, causing 7 phantom references to be pruned every time.
Now emits 'No external sources were used' instruction instead."
```

---

## Task 6: Conditional Hallucination Downgrade (Fix 5 — P1)

`_can_downgrade_delivery_integrity_issues()` must block `hallucination_verification_ungrounded` downgrade when no evidence exists.

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:1903-1920`
- Test: `backend/tests/unit/agents/test_execution_hallucination_downgrade.py`

### Step 1: Write the failing test

```python
# backend/tests/unit/agents/test_execution_hallucination_downgrade.py
"""Tests for conditional hallucination downgrade gating (Fix 5)."""

from unittest.mock import MagicMock


def _make_agent(*, has_sources: bool = False, has_evidence: bool = False):
    """Create a mock ExecutionAgent with controllable evidence state."""
    from app.domain.services.agents.execution import ExecutionAgent

    agent = MagicMock(spec=ExecutionAgent)
    agent._source_tracker = MagicMock()
    agent._source_tracker.get_collected_sources.return_value = (
        [MagicMock()] if has_sources else []
    )
    agent._research_execution_policy = MagicMock()
    agent._research_execution_policy.evidence_records = (
        [MagicMock()] if has_evidence else []
    )
    # Bind the real method
    agent._can_downgrade_delivery_integrity_issues = (
        ExecutionAgent._can_downgrade_delivery_integrity_issues.__get__(agent)
    )
    return agent


class TestHallucinationDowngradeGating:
    def test_ungrounded_not_downgradable_without_evidence(self):
        agent = _make_agent(has_sources=False, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["hallucination_verification_ungrounded: high ratio"]
        )
        assert result is False

    def test_ungrounded_downgradable_with_sources(self):
        agent = _make_agent(has_sources=True, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["hallucination_verification_ungrounded: high ratio"]
        )
        assert result is True

    def test_ungrounded_downgradable_with_evidence_records(self):
        agent = _make_agent(has_sources=False, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["hallucination_verification_ungrounded: high ratio"]
        )
        assert result is True

    def test_truncation_never_downgradable(self):
        """stream_truncation_unresolved is always non-downgradable regardless of evidence."""
        agent = _make_agent(has_sources=True, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["stream_truncation_unresolved: content cut off"]
        )
        assert result is False

    def test_citation_integrity_never_downgradable(self):
        agent = _make_agent(has_sources=True, has_evidence=True)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["citation_integrity_unresolved: broken refs"]
        )
        assert result is False

    def test_other_issues_always_downgradable(self):
        agent = _make_agent(has_sources=False, has_evidence=False)
        result = agent._can_downgrade_delivery_integrity_issues(
            ["coverage_gap: missing section"]
        )
        assert result is True
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_hallucination_downgrade.py -v --no-header -p no:cov -o addopts=`

Expected: `test_ungrounded_not_downgradable_without_evidence` FAILS (currently returns True).

### Step 3: Implement the conditional check

In `execution.py:_can_downgrade_delivery_integrity_issues()`, after the existing `non_downgradable_tokens` check loop (line 1916-1919), add before `return True`:

```python
# Fix 5: hallucination_verification_ungrounded requires evidence to be downgradable
for issue in issues:
    token = (issue or "").split(":", 1)[0].strip().lower()
    if token == "hallucination_verification_ungrounded":
        has_evidence = bool(
            self._source_tracker.get_collected_sources()
        ) or bool(
            getattr(self._research_execution_policy, "evidence_records", None)
        )
        if not has_evidence:
            return False
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_hallucination_downgrade.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all 6 tests)

### Step 5: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/agents/execution.py backend/tests/unit/agents/test_execution_hallucination_downgrade.py
git commit -m "fix(agents): block hallucination downgrade when no external evidence exists

hallucination_verification_ungrounded issues can no longer be downgraded
to warnings when source_tracker has no sources AND policy has no
evidence_records. Uses existing public APIs — no new fields added."
```

---

## Task 7: Charge Plan Updates to Execution Budget (Fix 7 — P1)

Add UPDATING case to `_transition_to()` so plan updates charge to the execution budget.

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:1382-1391`
- Test: `backend/tests/domain/services/flows/test_plan_act_budget_phase.py`

### Step 1: Write the failing test

```python
# backend/tests/domain/services/flows/test_plan_act_budget_phase.py
"""Tests for budget phase mapping during UPDATING transitions (Fix 7)."""

from unittest.mock import MagicMock, PropertyMock

from app.domain.models.state_model import AgentStatus


def _make_flow():
    """Create a minimal mock PlanActFlow for _transition_to testing."""
    from app.domain.services.flows.plan_act import PlanActFlow

    flow = MagicMock(spec=PlanActFlow)
    flow.status = AgentStatus.EXECUTING
    flow.planner = MagicMock()
    flow.executor = MagicMock()
    flow.verifier = None
    flow._plan_validation_failures = 0
    flow._error_recovery = MagicMock()
    flow._log_search_health = MagicMock()
    flow._rebalance_token_budget = MagicMock()
    # Bind the real _transition_to method
    flow._transition_to = PlanActFlow._transition_to.__get__(flow)
    return flow


def test_updating_sets_planner_phase_to_executing():
    """UPDATING transition should set planner._active_phase = 'executing'."""
    flow = _make_flow()
    flow._transition_to(AgentStatus.UPDATING)
    assert flow.planner._active_phase == "executing"


def test_planning_sets_planner_phase_to_planning():
    """PLANNING transition should set planner._active_phase = 'planning'."""
    flow = _make_flow()
    flow.status = AgentStatus.IDLE
    flow._transition_to(AgentStatus.PLANNING)
    assert flow.planner._active_phase == "planning"


def test_executing_clears_executor_phase():
    """EXECUTING transition should set executor._active_phase = None."""
    flow = _make_flow()
    flow.status = AgentStatus.PLANNING
    flow._transition_to(AgentStatus.EXECUTING)
    assert flow.executor._active_phase is None
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_budget_phase.py -v --no-header -p no:cov -o addopts=`

Expected: `test_updating_sets_planner_phase_to_executing` FAILS (no UPDATING case sets `_active_phase`).

### Step 3: Implement the one-line fix

In `plan_act.py:_transition_to()`, after line 1391 (`self.executor._active_phase = None  # All tools for summarization`), add:

```python
elif new_status == AgentStatus.UPDATING:
    self.planner._active_phase = "executing"
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/test_plan_act_budget_phase.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all 3 tests)

### Step 5: Run full plan_act tests

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/domain/services/flows/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS

### Step 6: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/domain/services/flows/plan_act.py backend/tests/domain/services/flows/test_plan_act_budget_phase.py
git commit -m "fix(flows): charge plan updates to execution budget via _active_phase

_transition_to() had no UPDATING case, so the planner's _active_phase
stayed 'planning' during plan updates between steps. This consumed
planning budget (15%) instead of execution budget (50%). One-line fix:
set planner._active_phase = 'executing' when entering UPDATING."
```

---

## Task 8: Explicit Timeout Profiles for Code-Generation Steps (Fix 1 — P2)

Add timeout profiles to `config_llm.py` and a `timeout_hint` parameter to `OpenAILLM.ask()` so code-generation steps get 180s instead of flat 90s.

**Files:**
- Modify: `backend/app/core/config_llm.py:139-146`
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py:1680-1790`
- Modify: `backend/app/domain/services/agents/execution.py` (pass hint from execute_step)
- Test: `backend/tests/infrastructure/external/llm/test_openai_timeout_profiles.py` (extend)
- Test: `backend/tests/unit/agents/test_execution_timeout_hint.py`

### Step 1: Write the failing tests for config and profile lookup

```python
# backend/tests/unit/agents/test_execution_timeout_hint.py
"""Tests for timeout hint propagation from execution to LLM (Fix 1)."""


def test_timeout_profiles_exist_in_config():
    """Config must expose llm_timeout_profiles with default, code_gen, summarize."""
    from app.core.config_llm import LLMSettingsMixin

    mixin = type("M", (LLMSettingsMixin,), {})()
    profiles = mixin.llm_timeout_profiles
    assert "default" in profiles
    assert "code_gen" in profiles
    assert "summarize" in profiles
    assert profiles["default"] == 90.0
    assert profiles["code_gen"] == 180.0
    assert profiles["summarize"] == 150.0
```

### Step 2: Run test to verify it fails

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_timeout_hint.py -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `llm_timeout_profiles` doesn't exist on `LLMSettingsMixin`.

### Step 3: Add timeout profiles to config

In `backend/app/core/config_llm.py`, after `llm_tool_request_timeout` (line 146), add:

```python
# Timeout profiles for different step types (Fix 1).
# Used by OpenAILLM.ask() when a timeout_hint is provided.
llm_timeout_profiles: dict[str, float] = {
    "default": 90.0,
    "code_gen": 180.0,
    "summarize": 150.0,
}
```

### Step 4: Run config test to verify it passes

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/test_execution_timeout_hint.py -v --no-header -p no:cov -o addopts=`

Expected: PASS

### Step 5: Write the failing test for ask() timeout_hint parameter

Append to `backend/tests/infrastructure/external/llm/test_openai_timeout_profiles.py`:

```python
def test_timeout_hint_code_gen_elevates_timeout() -> None:
    """When timeout_hint='code_gen', tool request timeout should use the code_gen profile."""
    from types import SimpleNamespace

    llm = _make_llm(api_base="https://api.kimi.com/coding/v1")

    settings = SimpleNamespace(
        llm_request_timeout=300.0,
        llm_stream_read_timeout=90.0,
        llm_tool_request_timeout=90.0,
        llm_timeout_profiles={"default": 90.0, "code_gen": 180.0, "summarize": 150.0},
    )

    with patch("app.infrastructure.external.llm.openai_llm.get_settings", return_value=settings):
        resolved = llm._resolve_tool_timeout(
            base_timeout=90.0,
            timeout_hint="code_gen",
        )

    assert resolved == 180.0


def test_timeout_hint_none_uses_default() -> None:
    """When timeout_hint is None, use the base timeout as-is."""
    from types import SimpleNamespace

    llm = _make_llm(api_base="https://api.kimi.com/coding/v1")

    settings = SimpleNamespace(
        llm_request_timeout=300.0,
        llm_stream_read_timeout=90.0,
        llm_tool_request_timeout=90.0,
        llm_timeout_profiles={"default": 90.0, "code_gen": 180.0, "summarize": 150.0},
    )

    with patch("app.infrastructure.external.llm.openai_llm.get_settings", return_value=settings):
        resolved = llm._resolve_tool_timeout(
            base_timeout=90.0,
            timeout_hint=None,
        )

    assert resolved == 90.0
```

### Step 6: Run test to verify it fails

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/infrastructure/external/llm/test_openai_timeout_profiles.py::test_timeout_hint_code_gen_elevates_timeout -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `_resolve_tool_timeout` doesn't exist.

### Step 7: Implement timeout hint in OpenAILLM

In `openai_llm.py`, add a new method to `OpenAILLM`:

```python
def _resolve_tool_timeout(
    self, base_timeout: float, timeout_hint: str | None
) -> float:
    """Resolve tool request timeout using profile hint if available."""
    if not timeout_hint:
        return base_timeout
    from app.core.config import get_settings

    settings = get_settings()
    profiles = getattr(settings, "llm_timeout_profiles", {})
    return profiles.get(timeout_hint, base_timeout)
```

In the `ask()` method signature (~line 1680), add `timeout_hint: str | None = None` parameter.

In the timeout calculation block (~line 1765), replace:
```python
tool_request_timeout = llm_tool_request_timeout
```
with:
```python
tool_request_timeout = self._resolve_tool_timeout(llm_tool_request_timeout, timeout_hint)
```

### Step 8: Run timeout tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/infrastructure/external/llm/test_openai_timeout_profiles.py -v --no-header -p no:cov -o addopts=`

Expected: PASS

### Step 9: Pass timeout_hint from execution.py

In `execution.py`, in the `execute_step()` method, find where `self.execute(execution_message)` is called (line ~493). The hint needs to be passed through to the LLM layer. Find the LLM call site within `execute()` and pass the hint.

In the `execute()` method, before the LLM `ask()` call, detect file-write tools:

```python
# Fix 1: Determine timeout hint based on available tools
_timeout_hint: str | None = None
if self._has_file_write_in_tools():
    _timeout_hint = "code_gen"
```

Add the helper:

```python
def _has_file_write_in_tools(self) -> bool:
    """Check if current tool set includes file_write/file_append."""
    if not self.tools:
        return False
    return any(
        getattr(t, "name", "") in {"file_write", "file_append"}
        for t in self.tools
    )
```

### Step 10: Run full execution + LLM test suite

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/unit/agents/ tests/infrastructure/external/llm/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS

### Step 11: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/core/config_llm.py backend/app/infrastructure/external/llm/openai_llm.py backend/app/domain/services/agents/execution.py backend/tests/infrastructure/external/llm/test_openai_timeout_profiles.py backend/tests/unit/agents/test_execution_timeout_hint.py
git commit -m "feat(llm): add timeout profiles for code-generation steps

Adds llm_timeout_profiles config dict (default=90s, code_gen=180s,
summarize=150s) and timeout_hint parameter to OpenAILLM.ask().
Execution passes code_gen hint when file_write tools are available,
preventing timeouts on large code generation requests."
```

---

## Task 9: Sandbox Queued Ownership with Bounded Wait (Fix 6 — P2)

Add `wait_for_ownership()` to `DockerSandbox` and use it in `agent_service.py` when `register_session()` returns None.

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py:1635-1680`
- Modify: `backend/app/application/services/agent_service.py:548-558`
- Modify: `backend/app/core/config.py` (add `sandbox_ownership_wait_timeout`)
- Test: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_ownership_wait.py`

### Step 1: Write the failing test

```python
# backend/tests/infrastructure/external/sandbox/test_docker_sandbox_ownership_wait.py
"""Tests for sandbox queued ownership with bounded wait (Fix 6)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


@pytest.mark.asyncio
async def test_wait_for_ownership_succeeds_when_liveness_expires():
    """wait_for_ownership should poll and succeed when previous owner's liveness key expires."""
    call_count = 0

    async def mock_register(address, session_id):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return None  # Still blocked
        return "previous-session"  # Succeeded on retry

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address="http://localhost:8083",
            session_id="new-session",
            timeout=10.0,
            poll_interval=0.1,
        )

    assert result is True
    assert call_count == 2


@pytest.mark.asyncio
async def test_wait_for_ownership_times_out():
    """wait_for_ownership should return False after timeout."""
    async def mock_register(address, session_id):
        return None  # Always blocked

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address="http://localhost:8083",
            session_id="new-session",
            timeout=0.5,
            poll_interval=0.1,
        )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_ownership_immediate_success():
    """If register_session succeeds immediately (non-None), return True."""
    async def mock_register(address, session_id):
        return "previous-session"

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address="http://localhost:8083",
            session_id="new-session",
            timeout=10.0,
            poll_interval=0.1,
        )

    assert result is True
```

### Step 2: Run tests to verify they fail

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/infrastructure/external/sandbox/test_docker_sandbox_ownership_wait.py -v --no-header -p no:cov -o addopts=`

Expected: FAIL — `wait_for_ownership` doesn't exist.

### Step 3: Implement wait_for_ownership

In `docker_sandbox.py`, after `register_session()` method (~line 1680), add:

```python
@classmethod
async def wait_for_ownership(
    cls,
    address: str,
    session_id: str,
    timeout: float = 60.0,
    poll_interval: float = 5.0,
) -> bool:
    """Poll register_session until ownership is acquired or timeout expires.

    Returns True if ownership was acquired, False on timeout.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await cls.register_session(address, session_id)
        if result is not None:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval, remaining))
    return False
```

### Step 4: Run tests to verify they pass

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/infrastructure/external/sandbox/test_docker_sandbox_ownership_wait.py -v --no-header -p no:cov -o addopts=`

Expected: PASS (all 3 tests)

### Step 5: Add config setting

In `backend/app/core/config.py`, in the sandbox-related settings section, add:

```python
sandbox_ownership_wait_timeout: float = 60.0
```

### Step 6: Integrate in agent_service.py

In `agent_service.py`, after line 553 (`previous_session = await DockerSandbox.register_session(address, session_id)`), replace the simple log with bounded wait:

```python
previous_session = await DockerSandbox.register_session(address, session_id)
if previous_session is None:
    # Fix 6: Wait for previous owner to release
    from app.core.config import get_settings

    wait_timeout = get_settings().sandbox_ownership_wait_timeout
    logger.info(
        "Sandbox %s ownership blocked — waiting up to %.0fs",
        address,
        wait_timeout,
    )
    acquired = await DockerSandbox.wait_for_ownership(
        address, session_id, timeout=wait_timeout
    )
    if not acquired:
        logger.warning(
            "Sandbox %s still owned after %.0fs — operating without sandbox",
            address,
            wait_timeout,
        )
elif previous_session:
    logger.info(
        f"Sandbox {address} was owned by session {previous_session}, "
        f"now reassigned to {session_id}"
    )
```

### Step 7: Run sandbox tests

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/infrastructure/external/sandbox/ -v --no-header -p no:cov -o addopts= -x`

Expected: PASS

### Step 8: Commit

```bash
cd /home/mac/Desktop/Pythinker-main
git add backend/app/infrastructure/external/sandbox/docker_sandbox.py backend/app/application/services/agent_service.py backend/app/core/config.py backend/tests/infrastructure/external/sandbox/test_docker_sandbox_ownership_wait.py
git commit -m "feat(sandbox): add queued ownership acquisition with bounded wait

When register_session() returns None (sandbox blocked by active session),
wait_for_ownership() polls every 5s up to sandbox_ownership_wait_timeout
(default 60s). If the timeout expires, agent operates without sandbox.
Prevents dev-mode BLOCKED errors from silently losing sandbox access."
```

---

## Task 10: Final Verification

### Step 1: Run the full backend test suite

Run: `cd /home/mac/Desktop/Pythinker-main && conda run -n pythinker python -m pytest tests/ -v --no-header -p no:cov -o addopts= --timeout=60`

Expected: All new tests pass, no regressions.

### Step 2: Run linting

Run: `cd /home/mac/Desktop/Pythinker-main/backend && conda run -n pythinker ruff check . && conda run -n pythinker ruff format --check .`

Expected: No errors.

### Step 3: Verify git log

Run: `git log --oneline -10`

Expected: 9 atomic commits (Tasks 1-9), each independently revertable.

---

## Summary

| Task | Fix | Files Modified | Tests Added | Priority |
|------|-----|---------------|-------------|----------|
| 1 | 4A — Evidence flag + gate | execution.py | test_execution_evidence_gate.py (10) | P0 |
| 2 | 4A — Retry injection | plan_act.py | test_plan_act_evidence_retry.py (4) | P0 |
| 3 | 4B — Synthesis backstop | execution.py | test_execution_synthesis_gate.py (3) | P0 |
| 4 | 3 — Security bypass | plan_act.py | test_plan_act_output_guardrails.py (2) | P0 |
| 5 | 2 — Phantom citations | prompts/execution.py | test_phantom_citations.py (3) | P0 |
| 6 | 5 — Hallucination downgrade | execution.py | test_execution_hallucination_downgrade.py (6) | P1 |
| 7 | 7 — Budget phase | plan_act.py | test_plan_act_budget_phase.py (3) | P1 |
| 8 | 1 — Timeout profiles | config_llm.py, openai_llm.py, execution.py | test_openai_timeout_profiles.py (2), test_execution_timeout_hint.py (1) | P2 |
| 9 | 6 — Sandbox ownership | docker_sandbox.py, agent_service.py, config.py | test_docker_sandbox_ownership_wait.py (3) | P2 |
| 10 | — Final verification | — | — | — |
