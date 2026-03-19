"""Shared test fixtures for cross-module reuse.

Import these fixtures into any test's conftest.py:

    from tests.conftest_shared import mock_settings, mock_session, fake_user_id

Available fixtures:
- mock_settings: Pre-configured Settings instance for testing
- mock_session: A minimal Session domain object
- fake_user_id: A deterministic user ID string
- mock_llm_response: A canned LLM response for tool/chat tests
- async_mock: An AsyncMock helper with common patterns
"""

import pytest


@pytest.fixture
def fake_user_id() -> str:
    """Return a deterministic user ID for testing."""
    return "test-user-00000000-0000-0000-0000-000000000000"
