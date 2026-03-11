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

    assert _should_inject_evidence_retry(attempt=1, step_error="Research step completed without external evidence")


def test_should_not_inject_on_first_attempt():
    """First attempt (attempt=0) should never inject evidence retry."""
    from app.domain.services.flows.plan_act import _should_inject_evidence_retry

    assert not _should_inject_evidence_retry(attempt=0, step_error="Research step completed without external evidence")


def test_should_not_inject_for_other_errors():
    """Non-evidence errors should not trigger injection."""
    from app.domain.services.flows.plan_act import _should_inject_evidence_retry

    assert not _should_inject_evidence_retry(attempt=1, step_error="Tool execution failed")
    assert not _should_inject_evidence_retry(attempt=1, step_error=None)
