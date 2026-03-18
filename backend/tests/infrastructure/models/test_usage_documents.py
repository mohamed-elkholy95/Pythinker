import pytest

from app.infrastructure.models.documents import AgentRunDocument, AgentStepDocument, PricingSnapshotDocument

pytestmark = pytest.mark.unit


def test_agent_usage_documents_use_default_factories_for_runtime_timestamps() -> None:
    assert AgentRunDocument.model_fields["started_at"].default_factory is not None
    assert AgentStepDocument.model_fields["started_at"].default_factory is not None
    assert PricingSnapshotDocument.model_fields["source_retrieved_at"].default_factory is not None
