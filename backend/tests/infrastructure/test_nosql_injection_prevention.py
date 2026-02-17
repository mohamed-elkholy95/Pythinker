"""Tests for NoSQL injection prevention in MongoDB repositories.

Validates that:
1. Regex injection is blocked in connector and skill search queries
2. Sort field injection is blocked in skill marketplace queries
3. Arbitrary field injection is blocked in session update_by_id
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.exceptions.base import BusinessRuleViolation, SecurityViolation
from app.infrastructure.repositories.mongo_connector_repository import (
    MongoConnectorRepository,
)
from app.infrastructure.repositories.mongo_session_repository import (
    ALLOWED_SESSION_UPDATE_FIELDS,
    MongoSessionRepository,
)
from app.infrastructure.repositories.mongo_skill_repository import (
    ALLOWED_SORT_FIELDS,
    MongoSkillRepository,
    SkillSearchFilters,
)

# =============================================================================
# 1. Regex Injection Prevention Tests
# =============================================================================


class TestConnectorSearchRegexEscaping:
    """Tests that MongoConnectorRepository.search escapes regex metacharacters."""

    @pytest.mark.parametrize(
        "malicious_query",
        [
            ".*",
            "^admin$",
            "a|b",
            "test(.*)",
            "[a-z]+",
            "foo{1,3}",
            "my-connector_v2",
        ],
    )
    def test_regex_escape_produces_safe_pattern(self, malicious_query: str) -> None:
        """Verify re.escape neutralizes regex metacharacters."""
        escaped = re.escape(malicious_query)
        # The escaped pattern should match only the literal input string
        compiled = re.compile(escaped)
        assert compiled.fullmatch(malicious_query) is not None
        # It should NOT match arbitrary strings
        assert compiled.fullmatch("totally different text") is None

    @pytest.mark.asyncio
    async def test_search_escapes_query_in_regex(self) -> None:
        """Verify the search method passes escaped query to MongoDB $regex."""
        repo = MongoConnectorRepository()

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        with patch("app.infrastructure.repositories.mongo_connector_repository.ConnectorDocument") as mock_doc:
            mock_doc.find.return_value = mock_cursor

            await repo.search(query=".*admin.*")

            # Verify the query passed to find() has escaped regex
            call_args = mock_doc.find.call_args[0][0]
            assert "$or" in call_args
            for condition in call_args["$or"]:
                for regex_spec in condition.values():
                    assert regex_spec["$regex"] == re.escape(".*admin.*")
                    assert regex_spec["$options"] == "i"

    @pytest.mark.asyncio
    async def test_search_normal_query_works(self) -> None:
        """Verify normal search strings pass through (escaped but still functional)."""
        repo = MongoConnectorRepository()

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        with patch("app.infrastructure.repositories.mongo_connector_repository.ConnectorDocument") as mock_doc:
            mock_doc.find.return_value = mock_cursor

            await repo.search(query="github api")

            call_args = mock_doc.find.call_args[0][0]
            for condition in call_args["$or"]:
                for regex_spec in condition.values():
                    # re.escape is applied; the escaped value should equal re.escape("github api")
                    assert regex_spec["$regex"] == re.escape("github api")

    @pytest.mark.asyncio
    async def test_search_without_query_has_no_regex(self) -> None:
        """Verify searching without a query omits the $or regex clause."""
        repo = MongoConnectorRepository()

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        with patch("app.infrastructure.repositories.mongo_connector_repository.ConnectorDocument") as mock_doc:
            mock_doc.find.return_value = mock_cursor

            await repo.search(query=None)

            call_args = mock_doc.find.call_args[0][0]
            assert "$or" not in call_args


class TestSkillSearchRegexEscaping:
    """Tests that SkillSearchFilters.to_mongo_query escapes regex metacharacters."""

    @pytest.mark.parametrize(
        "malicious_query",
        [
            ".*",
            "^admin$",
            "a|b",
            "test(.*)",
            "[a-z]+",
            "foo{1,3}",
            "$where",
            "(?=.*password)",
        ],
    )
    def test_to_mongo_query_escapes_regex(self, malicious_query: str) -> None:
        """Verify to_mongo_query escapes regex metacharacters in search query."""
        filters = SkillSearchFilters(query=malicious_query)
        mongo_query = filters.to_mongo_query()

        assert "$or" in mongo_query
        expected_escaped = re.escape(malicious_query)
        for condition in mongo_query["$or"]:
            for regex_spec in condition.values():
                assert regex_spec["$regex"] == expected_escaped
                assert regex_spec["$options"] == "i"

    def test_to_mongo_query_normal_text(self) -> None:
        """Verify normal text is escaped consistently."""
        filters = SkillSearchFilters(query="data analysis")
        mongo_query = filters.to_mongo_query()

        for condition in mongo_query["$or"]:
            for regex_spec in condition.values():
                assert regex_spec["$regex"] == re.escape("data analysis")

    def test_to_mongo_query_no_query(self) -> None:
        """Verify no $or clause when query is None."""
        filters = SkillSearchFilters(query=None)
        mongo_query = filters.to_mongo_query()
        assert "$or" not in mongo_query


# =============================================================================
# 2. Sort Field Validation Tests
# =============================================================================


def _build_beanie_find_mock() -> MagicMock:
    """Build a mock that simulates the Beanie FindMany query chain.

    Beanie uses a fluent interface: find().sort().skip().limit().to_list()
    where to_list() is awaited. We also mock .count() as an async method.

    Each method in the chain returns a new mock that supports the next
    method, ending with an AsyncMock for to_list().
    """
    # Terminal node: to_list() is async and returns empty list
    mock_terminal = MagicMock()
    mock_terminal.to_list = AsyncMock(return_value=[])

    # limit() returns the terminal node
    mock_skip = MagicMock()
    mock_skip.limit = MagicMock(return_value=mock_terminal)

    # sort() returns a mock with .skip()
    mock_sort = MagicMock()
    mock_sort.skip = MagicMock(return_value=mock_skip)

    # find() returns a mock with .sort() and .count()
    mock_find = MagicMock()
    mock_find.sort = MagicMock(return_value=mock_sort)
    mock_find.count = AsyncMock(return_value=0)

    return mock_find


class TestSkillSortFieldValidation:
    """Tests that sort_by is validated against the allowlist."""

    def test_allowed_sort_fields_contains_expected_values(self) -> None:
        """Verify the allowlist contains all expected sort fields."""
        expected = {"community_rating", "install_count", "created_at", "updated_at", "name"}
        assert expected == ALLOWED_SORT_FIELDS

    def test_allowed_sort_fields_is_frozenset(self) -> None:
        """Verify the allowlist is immutable."""
        assert isinstance(ALLOWED_SORT_FIELDS, frozenset)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("valid_field", sorted(ALLOWED_SORT_FIELDS))
    async def test_search_accepts_valid_sort_fields(self, valid_field: str) -> None:
        """Verify all allowlisted sort fields are accepted."""
        repo = MongoSkillRepository()
        filters = SkillSearchFilters(is_public=True)

        mock_find = _build_beanie_find_mock()

        with patch("app.infrastructure.repositories.mongo_skill_repository.SkillDocument") as mock_doc:
            mock_doc.find.return_value = mock_find

            # Should not raise
            skills, total = await repo.search(filters, sort_by=valid_field, sort_order=-1)
            assert total == 0
            assert skills == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malicious_field",
        [
            "$where",
            "__proto__",
            "password",
            "events.0.data",
            "constructor",
            "toString",
            "user_id",
            "$gt",
            "admin",
            "",
        ],
    )
    async def test_search_rejects_invalid_sort_fields(self, malicious_field: str) -> None:
        """Verify invalid/malicious sort fields are rejected with SecurityViolation."""
        repo = MongoSkillRepository()
        filters = SkillSearchFilters(is_public=True)

        with pytest.raises(SecurityViolation, match="Invalid sort field"):
            await repo.search(filters, sort_by=malicious_field, sort_order=-1)

    @pytest.mark.asyncio
    async def test_search_reject_message_lists_allowed_fields(self) -> None:
        """Verify the error message includes the list of allowed fields."""
        repo = MongoSkillRepository()
        filters = SkillSearchFilters(is_public=True)

        with pytest.raises(SecurityViolation, match="community_rating") as exc_info:
            await repo.search(filters, sort_by="$evil", sort_order=-1)

        error_msg = str(exc_info.value)
        for field in ALLOWED_SORT_FIELDS:
            assert field in error_msg


# =============================================================================
# 3. Session update_by_id Field Allowlist Tests
# =============================================================================


class TestSessionUpdateByIdFieldAllowlist:
    """Tests that update_by_id validates field names against the allowlist."""

    def test_allowed_fields_is_frozenset(self) -> None:
        """Verify the allowlist is immutable."""
        assert isinstance(ALLOWED_SESSION_UPDATE_FIELDS, frozenset)

    def test_allowed_fields_contains_workspace_fields(self) -> None:
        """Verify workspace-related fields are in the allowlist."""
        workspace_fields = {
            "workspace_structure",
            "project_name",
            "project_path",
            "template_id",
            "template_used",
        }
        assert workspace_fields.issubset(ALLOWED_SESSION_UPDATE_FIELDS)

    def test_allowed_fields_contains_execution_fields(self) -> None:
        """Verify execution metadata fields are in the allowlist."""
        execution_fields = {"complexity_score", "iteration_limit_override"}
        assert execution_fields.issubset(ALLOWED_SESSION_UPDATE_FIELDS)

    @pytest.mark.asyncio
    async def test_update_by_id_accepts_allowed_fields(self) -> None:
        """Verify allowed fields pass validation."""
        repo = MongoSessionRepository()

        mock_result = MagicMock()
        mock_update = AsyncMock(return_value=mock_result)
        mock_find = MagicMock()
        mock_find.update = mock_update

        with patch("app.infrastructure.repositories.mongo_session_repository.SessionDocument") as mock_doc:
            mock_doc.find_one.return_value = mock_find

            # Should not raise
            await repo.update_by_id(
                "session-123",
                {
                    "workspace_structure": {"src": "source code"},
                    "complexity_score": 0.75,
                },
            )

            # Verify MongoDB update was called
            mock_update.assert_called_once()
            update_payload = mock_update.call_args[0][0]
            assert "$set" in update_payload
            assert update_payload["$set"]["workspace_structure"] == {"src": "source code"}
            assert update_payload["$set"]["complexity_score"] == 0.75
            assert "updated_at" in update_payload["$set"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malicious_field",
        [
            "user_id",
            "session_id",
            "agent_id",
            "events",
            "$set",
            "$unset",
            "__proto__",
            "password",
            "is_admin",
            "role",
        ],
    )
    async def test_update_by_id_rejects_disallowed_fields(self, malicious_field: str) -> None:
        """Verify disallowed fields raise BusinessRuleViolation before reaching MongoDB."""
        repo = MongoSessionRepository()

        with pytest.raises(BusinessRuleViolation, match="Disallowed update fields"):
            await repo.update_by_id(
                "session-123",
                {malicious_field: "injected_value"},
            )

    @pytest.mark.asyncio
    async def test_update_by_id_rejects_mixed_allowed_and_disallowed(self) -> None:
        """Verify that even one disallowed field causes rejection of entire update."""
        repo = MongoSessionRepository()

        with pytest.raises(BusinessRuleViolation, match="Disallowed update fields"):
            await repo.update_by_id(
                "session-123",
                {
                    "workspace_structure": {"valid": "data"},  # allowed
                    "user_id": "attacker-id",  # NOT allowed
                },
            )

    @pytest.mark.asyncio
    async def test_update_by_id_empty_updates_is_noop(self) -> None:
        """Verify empty updates dict is a no-op (no DB call)."""
        repo = MongoSessionRepository()

        with patch("app.infrastructure.repositories.mongo_session_repository.SessionDocument") as mock_doc:
            await repo.update_by_id("session-123", {})

            # No MongoDB query should be made
            mock_doc.find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_by_id_error_message_lists_disallowed_fields(self) -> None:
        """Verify the error message identifies which specific fields are disallowed."""
        repo = MongoSessionRepository()

        with pytest.raises(BusinessRuleViolation) as exc_info:
            await repo.update_by_id(
                "session-123",
                {"events": [], "user_id": "attacker"},
            )

        error_msg = str(exc_info.value)
        assert "events" in error_msg
        assert "user_id" in error_msg

    @pytest.mark.asyncio
    async def test_update_by_id_does_not_mutate_original_updates(self) -> None:
        """Verify the original updates dict is not mutated by adding updated_at."""
        repo = MongoSessionRepository()

        original_updates = {"complexity_score": 0.5}

        mock_result = MagicMock()
        mock_update = AsyncMock(return_value=mock_result)
        mock_find = MagicMock()
        mock_find.update = mock_update

        with patch("app.infrastructure.repositories.mongo_session_repository.SessionDocument") as mock_doc:
            mock_doc.find_one.return_value = mock_find

            await repo.update_by_id("session-123", original_updates)

            # Original dict should not have updated_at added
            assert "updated_at" not in original_updates


# =============================================================================
# 4. Integration-style validation tests
# =============================================================================


class TestRegexInjectionIntegration:
    """Cross-cutting tests to verify regex injection patterns are neutralized."""

    @pytest.mark.parametrize(
        "attack_pattern,description",
        [
            (".*", "match everything"),
            ("^$", "match empty string"),
            ("a{999999999}", "ReDoS exponential backtracking"),
            ("(?:a+)+$", "ReDoS catastrophic backtracking"),
            ("(a|b|c|.*)", "alternation with wildcard"),
            ("[\\x00-\\xFF]", "byte range match"),
        ],
    )
    def test_escape_neutralizes_attack_patterns(self, attack_pattern: str, description: str) -> None:
        """Verify re.escape neutralizes known regex attack patterns."""
        escaped = re.escape(attack_pattern)
        # The escaped pattern should only match the literal string
        compiled = re.compile(escaped)
        assert compiled.fullmatch(attack_pattern) is not None
        # It should NOT match arbitrary strings
        assert compiled.fullmatch("some random text") is None
