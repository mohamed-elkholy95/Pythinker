"""Tests for Tool Argument Canonicalization (Workstream C)

Test coverage for argument alias mapping and canonicalization.
"""

import pytest

from app.domain.services.tools.argument_canonicalizer import ArgumentCanonicalizer
from app.infrastructure.observability.agent_metrics import (
    agent_tool_args_canonicalized,
    agent_tool_args_rejected,
)


class TestArgumentCanonicalizer:
    """Test suite for argument canonicalization."""

    @pytest.fixture
    def canonicalizer(self):
        """Create canonicalizer instance."""
        return ArgumentCanonicalizer()

    def test_known_alias_mapping_browser_url(self, canonicalizer):
        """Test browser tool url aliases are mapped to canonical name."""
        # Test 'uri' -> 'url'
        args = {"uri": "https://example.com", "timeout_ms": 5000}
        canonical = canonicalizer.canonicalize("browser", args)

        assert "url" in canonical
        assert canonical["url"] == "https://example.com"
        assert "uri" not in canonical

    def test_known_alias_mapping_browser_timeout(self, canonicalizer):
        """Test browser tool timeout aliases."""
        # Test 'timeout_ms' -> 'timeout'
        args = {"url": "https://example.com", "timeout_ms": 5000}
        canonical = canonicalizer.canonicalize("browser", args)

        assert "timeout" in canonical
        assert canonical["timeout"] == 5000
        assert "timeout_ms" not in canonical

    def test_known_alias_mapping_search(self, canonicalizer):
        """Test search tool query aliases."""
        # Test 'q' -> 'query'
        args = {"q": "test search", "limit": 10}
        canonical = canonicalizer.canonicalize("search", args)

        assert "query" in canonical
        assert canonical["query"] == "test search"
        assert "q" not in canonical

        # Test 'limit' -> 'max_results'
        assert "max_results" in canonical
        assert canonical["max_results"] == 10
        assert "limit" not in canonical

    def test_known_alias_mapping_file_read(self, canonicalizer):
        """Test file_read tool path aliases."""
        # Test 'path' -> 'file_path'
        args = {"path": "/tmp/test.txt", "enc": "utf-8"}
        canonical = canonicalizer.canonicalize("file_read", args)

        assert "file_path" in canonical
        assert canonical["file_path"] == "/tmp/test.txt"
        assert "path" not in canonical

        # Test 'enc' -> 'encoding'
        assert "encoding" in canonical
        assert canonical["encoding"] == "utf-8"
        assert "enc" not in canonical

    def test_multiple_aliases_in_same_call(self, canonicalizer):
        """Test multiple aliases canonicalized in single call."""
        args = {
            "uri": "https://example.com",
            "timeout_ms": 5000,
            "wait_for_selector": ".content",
        }
        canonical = canonicalizer.canonicalize("browser", args)

        # All aliases should be canonicalized
        assert canonical == {
            "url": "https://example.com",
            "timeout": 5000,
            "wait_for": ".content",
        }

    def test_non_alias_fields_preserved(self, canonicalizer):
        """Test non-alias fields are kept as-is."""
        args = {
            "url": "https://example.com",  # Already canonical
            "custom_field": "value",  # Not an alias
        }
        canonical = canonicalizer.canonicalize("browser", args)

        assert canonical["url"] == "https://example.com"
        assert canonical["custom_field"] == "value"

    def test_unknown_tool_no_canonicalization(self, canonicalizer):
        """Test unknown tools pass through unchanged."""
        args = {"uri": "https://example.com", "custom": "value"}
        canonical = canonicalizer.canonicalize("unknown_tool", args)

        # Should return unchanged
        assert canonical == args

    def test_validate_no_unknown_fields_valid(self, canonicalizer):
        """Test validation passes when all fields are known."""
        canonical_args = {"url": "https://example.com", "timeout": 5000}
        known_fields = {"url", "timeout", "wait_for"}

        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical_args, known_fields)

        assert valid is True
        assert unknown == []

    def test_validate_no_unknown_fields_invalid(self, canonicalizer):
        """Test validation fails when unknown fields present."""
        canonical_args = {
            "url": "https://example.com",
            "unknown_field": "value",
            "another_unknown": "test",
        }
        known_fields = {"url", "timeout"}

        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical_args, known_fields)

        assert valid is False
        assert set(unknown) == {"unknown_field", "another_unknown"}

    def test_get_canonical_name(self, canonicalizer):
        """Test getting canonical name for an alias."""
        # Known alias
        assert canonicalizer.get_canonical_name("browser", "uri") == "url"
        assert canonicalizer.get_canonical_name("browser", "timeout_ms") == "timeout"
        assert canonicalizer.get_canonical_name("search", "q") == "query"

        # Already canonical
        assert canonicalizer.get_canonical_name("browser", "url") == "url"

        # Unknown tool or field
        assert canonicalizer.get_canonical_name("unknown", "field") == "field"

    def test_add_alias_rule_dynamic(self, canonicalizer):
        """Test adding alias rules dynamically."""
        # Add new rule for custom tool
        canonicalizer.add_alias_rule(
            tool_name="custom_tool",
            canonical_name="endpoint",
            aliases=["url", "uri", "api_url"],
        )

        # Test newly added rule
        args = {"url": "https://api.example.com"}
        canonical = canonicalizer.canonicalize("custom_tool", args)

        assert "endpoint" in canonical
        assert canonical["endpoint"] == "https://api.example.com"
        assert "url" not in canonical

    def test_canonicalization_metrics_incremented(self, canonicalizer):
        """Test canonicalization metrics are tracked."""
        initial_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})

        args = {"uri": "https://example.com"}
        canonicalizer.canonicalize("browser", args)

        final_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})

        assert final_count > initial_count

    def test_rejection_metrics_incremented(self, canonicalizer):
        """Test rejection metrics tracked for unknown fields."""
        initial_count = agent_tool_args_rejected.get({"tool_name": "browser", "rejection_reason": "unknown_field"})

        args = {"url": "https://example.com", "bad_field": "value"}
        known_fields = {"url", "timeout"}

        canonicalizer.validate_no_unknown_fields("browser", args, known_fields)

        final_count = agent_tool_args_rejected.get({"tool_name": "browser", "rejection_reason": "unknown_field"})

        assert final_count > initial_count

    def test_security_no_broad_coercion(self, canonicalizer):
        """Test that unknown fields are NOT silently coerced (security)."""
        # Unknown field should remain in output for Pydantic to reject
        args = {"url": "https://example.com", "malicious_field": "exploit"}
        canonical = canonicalizer.canonicalize("browser", args)

        # Unknown field should still be present (not silently removed)
        assert "malicious_field" in canonical
        assert canonical["malicious_field"] == "exploit"

        # Validation should catch it
        known_fields = {"url", "timeout"}
        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical, known_fields)

        assert valid is False
        assert "malicious_field" in unknown

    def test_empty_args(self, canonicalizer):
        """Test canonicalization with empty args dict."""
        args = {}
        canonical = canonicalizer.canonicalize("browser", args)

        assert canonical == {}

    def test_case_sensitivity(self, canonicalizer):
        """Test that aliases are case-sensitive."""
        # 'URI' (uppercase) is NOT recognized as 'uri' alias
        args = {"URI": "https://example.com"}
        canonical = canonicalizer.canonicalize("browser", args)

        # Should NOT be canonicalized (case mismatch)
        assert "URI" in canonical
        assert "url" not in canonical
