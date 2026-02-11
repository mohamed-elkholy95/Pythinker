"""Integration Tests for Argument Canonicalization (E2E)

End-to-end tests for tool argument canonicalization.
"""

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.domain.services.tools.argument_canonicalizer import ArgumentCanonicalizer
from app.infrastructure.observability.agent_metrics import (
    agent_tool_args_canonicalized,
    agent_tool_args_rejected,
)


class TestCanonicalizationE2E:
    """End-to-end test suite for argument canonicalization."""

    @pytest.fixture
    def canonicalizer(self):
        """Create canonicalizer instance."""
        return ArgumentCanonicalizer()

    @pytest.mark.asyncio
    async def test_argument_canonicalization(self, canonicalizer):
        """E2E: Tool argument aliases canonicalized before validation."""
        # Scenario: Browser tool call with aliases
        raw_args = {
            "uri": "https://example.com",  # Alias for 'url'
            "timeout_ms": 5000,  # Alias for 'timeout'
            "wait_for_selector": ".content",  # Alias for 'wait_for'
        }

        # Step 1: Track initial metrics
        initial_uri_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})
        initial_timeout_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "timeout_ms"})

        # Step 2: Canonicalize arguments
        canonical_args = canonicalizer.canonicalize("browser", raw_args)

        # Step 3: Verify aliases mapped to canonical names
        assert "url" in canonical_args
        assert canonical_args["url"] == "https://example.com"
        assert "uri" not in canonical_args  # Alias removed

        assert "timeout" in canonical_args
        assert canonical_args["timeout"] == 5000
        assert "timeout_ms" not in canonical_args  # Alias removed

        assert "wait_for" in canonical_args
        assert canonical_args["wait_for"] == ".content"
        assert "wait_for_selector" not in canonical_args  # Alias removed

        # Step 4: Verify metrics incremented
        final_uri_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})
        final_timeout_count = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "timeout_ms"})

        assert final_uri_count > initial_uri_count
        assert final_timeout_count > initial_timeout_count

        # Step 5: Validate canonical args with Pydantic (simulate real validation)
        class BrowserArgs(BaseModel):
            url: str
            timeout: int = Field(default=3000)
            wait_for: str | None = None

        # Should validate successfully
        validated = BrowserArgs(**canonical_args)
        assert validated.url == "https://example.com"
        assert validated.timeout == 5000
        assert validated.wait_for == ".content"

    @pytest.mark.asyncio
    async def test_unknown_fields_rejected(self, canonicalizer):
        """E2E: Unknown fields rejected after canonicalization."""
        # Scenario: Args with unknown field
        args = {
            "url": "https://example.com",
            "timeout": 5000,
            "malicious_field": "exploit_attempt",  # Unknown field
        }

        # Step 1: Canonicalize (unknown field preserved)
        canonical_args = canonicalizer.canonicalize("browser", args)

        # Unknown field should still be present (not silently removed)
        assert "malicious_field" in canonical_args

        # Step 2: Validate against known fields
        known_fields = {"url", "timeout", "wait_for", "screenshot"}

        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical_args, known_fields)

        # Step 3: Verify validation failed
        assert valid is False
        assert "malicious_field" in unknown

        # Step 4: Verify rejection metric tracked
        rejection_count = agent_tool_args_rejected.get({"tool_name": "browser", "rejection_reason": "unknown_field"})
        assert rejection_count > 0

        # Step 5: Pydantic validation should also reject
        class BrowserArgs(BaseModel):
            url: str
            timeout: int = Field(default=3000)
            wait_for: str | None = None

            class Config:
                extra = "forbid"  # Reject unknown fields

        with pytest.raises(ValidationError) as exc_info:
            BrowserArgs(**canonical_args)

        # Verify error mentions malicious_field
        error_str = str(exc_info.value)
        assert "malicious_field" in error_str

    @pytest.mark.asyncio
    async def test_canonicalization_metrics_tracked(self, canonicalizer):
        """E2E: Canonicalization metrics incremented correctly."""
        # Test multiple tools and aliases

        # Browser: uri -> url
        initial_browser_uri = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})

        canonicalizer.canonicalize("browser", {"uri": "https://test.com"})

        final_browser_uri = agent_tool_args_canonicalized.get({"tool_name": "browser", "alias_type": "uri"})
        assert final_browser_uri > initial_browser_uri

        # Search: q -> query
        initial_search_q = agent_tool_args_canonicalized.get({"tool_name": "search", "alias_type": "q"})

        canonicalizer.canonicalize("search", {"q": "test query"})

        final_search_q = agent_tool_args_canonicalized.get({"tool_name": "search", "alias_type": "q"})
        assert final_search_q > initial_search_q

        # File read: path -> file_path
        initial_file_path = agent_tool_args_canonicalized.get({"tool_name": "file_read", "alias_type": "path"})

        canonicalizer.canonicalize("file_read", {"path": "/test.txt"})

        final_file_path = agent_tool_args_canonicalized.get({"tool_name": "file_read", "alias_type": "path"})
        assert final_file_path > initial_file_path

    @pytest.mark.asyncio
    async def test_security_no_silent_coercion(self, canonicalizer):
        """E2E: No broad silent coercion (security test)."""
        # Security requirement: Unknown fields must NOT be silently removed
        # They must be preserved so Pydantic validation can reject them

        # Scenario: Attacker tries SQL injection via unknown field
        malicious_args = {
            "url": "https://example.com",
            "sql_injection": "'; DROP TABLE users; --",
            "xss_payload": "<script>alert('XSS')</script>",
        }

        # Step 1: Canonicalize
        canonical = canonicalizer.canonicalize("browser", malicious_args)

        # Step 2: CRITICAL: Malicious fields must be preserved
        assert "sql_injection" in canonical
        assert "xss_payload" in canonical
        assert canonical["sql_injection"] == "'; DROP TABLE users; --"
        assert canonical["xss_payload"] == "<script>alert('XSS')</script>"

        # Step 3: Validation must detect and reject them
        known_fields = {"url", "timeout"}
        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical, known_fields)

        assert valid is False
        assert "sql_injection" in unknown
        assert "xss_payload" in unknown

        # Step 4: Rejection metric should be incremented
        rejection_count = agent_tool_args_rejected.get({"tool_name": "browser", "rejection_reason": "unknown_field"})
        assert rejection_count > 0

        # Step 5: Demonstrate that silent removal would be DANGEROUS
        # If we silently removed unknown fields, attacker could bypass validation
        # by sending: {"url": "https://evil.com", "secret_field": "admin_mode"}
        # Silent removal would result in: {"url": "https://evil.com"}
        # Which would pass validation, but context is lost for security audit

        # Our approach: Preserve and explicitly reject
        # Result: {"url": "https://evil.com", "secret_field": "admin_mode"}
        # Validation fails, security team can audit malicious attempt

    @pytest.mark.asyncio
    async def test_multiple_tools_end_to_end(self, canonicalizer):
        """E2E: Canonicalization works across different tools."""
        # Test 1: Browser tool
        browser_args = {"uri": "https://example.com", "timeout_ms": 3000}
        browser_canonical = canonicalizer.canonicalize("browser", browser_args)

        assert browser_canonical == {"url": "https://example.com", "timeout": 3000}

        # Test 2: Search tool
        search_args = {"q": "python tutorials", "limit": 20}
        search_canonical = canonicalizer.canonicalize("search", search_args)

        assert search_canonical == {"query": "python tutorials", "max_results": 20}

        # Test 3: File read tool
        file_args = {"path": "/data/file.txt", "enc": "utf-8"}
        file_canonical = canonicalizer.canonicalize("file_read", file_args)

        assert file_canonical == {"file_path": "/data/file.txt", "encoding": "utf-8"}

        # Test 4: Unknown tool (pass through)
        unknown_args = {"custom": "value"}
        unknown_canonical = canonicalizer.canonicalize("custom_tool", unknown_args)

        assert unknown_canonical == unknown_args  # Unchanged

    @pytest.mark.asyncio
    async def test_dynamic_alias_registration(self, canonicalizer):
        """E2E: Dynamic alias rules can be added at runtime."""
        # Step 1: Add custom alias rule
        canonicalizer.add_alias_rule(
            tool_name="api_client",
            canonical_name="endpoint",
            aliases=["url", "uri", "api_url", "target"],
        )

        # Step 2: Test new rule
        args = {"api_url": "https://api.example.com/v1/users"}
        canonical = canonicalizer.canonicalize("api_client", args)

        # Verify alias mapped
        assert "endpoint" in canonical
        assert canonical["endpoint"] == "https://api.example.com/v1/users"
        assert "api_url" not in canonical

        # Step 3: Test all aliases for same canonical name
        for alias in ["url", "uri", "target"]:
            test_args = {alias: "https://test.com"}
            result = canonicalizer.canonicalize("api_client", test_args)

            assert "endpoint" in result
            assert result["endpoint"] == "https://test.com"
            assert alias not in result

    @pytest.mark.asyncio
    async def test_mixed_canonical_and_alias_fields(self, canonicalizer):
        """E2E: Handles mix of canonical names and aliases."""
        # Scenario: Some args already canonical, some are aliases
        args = {
            "url": "https://example.com",  # Already canonical
            "timeout_ms": 5000,  # Alias -> timeout
            "screenshot": True,  # Already canonical
        }

        canonical = canonicalizer.canonicalize("browser", args)

        # Canonical names preserved
        assert canonical["url"] == "https://example.com"
        assert canonical["screenshot"] is True

        # Alias mapped
        assert canonical["timeout"] == 5000
        assert "timeout_ms" not in canonical

    @pytest.mark.asyncio
    async def test_get_canonical_name_utility(self, canonicalizer):
        """E2E: get_canonical_name returns correct mappings."""
        # Known aliases
        assert canonicalizer.get_canonical_name("browser", "uri") == "url"
        assert canonicalizer.get_canonical_name("browser", "timeout_ms") == "timeout"
        assert canonicalizer.get_canonical_name("search", "q") == "query"
        assert canonicalizer.get_canonical_name("search", "limit") == "max_results"

        # Already canonical
        assert canonicalizer.get_canonical_name("browser", "url") == "url"
        assert canonicalizer.get_canonical_name("browser", "timeout") == "timeout"

        # Unknown tool or field
        assert canonicalizer.get_canonical_name("unknown", "field") == "field"

    @pytest.mark.asyncio
    async def test_empty_args_handling(self, canonicalizer):
        """E2E: Empty args dict handled correctly."""
        empty = {}
        canonical = canonicalizer.canonicalize("browser", empty)

        assert canonical == {}
        assert len(canonical) == 0

    @pytest.mark.asyncio
    async def test_validation_with_pydantic(self, canonicalizer):
        """E2E: Canonicalized args work seamlessly with Pydantic."""

        # Define Pydantic models for tool args
        class BrowserArgs(BaseModel):
            url: str
            timeout: int = Field(default=3000, ge=0)
            wait_for: str | None = None
            screenshot: bool = False

            class Config:
                extra = "forbid"

        class SearchArgs(BaseModel):
            query: str
            max_results: int = Field(default=10, ge=1, le=100)

            class Config:
                extra = "forbid"

        # Test 1: Browser with aliases
        browser_raw = {
            "uri": "https://example.com",
            "timeout_ms": 5000,
            "screenshot": True,
        }

        browser_canonical = canonicalizer.canonicalize("browser", browser_raw)
        browser_validated = BrowserArgs(**browser_canonical)

        assert browser_validated.url == "https://example.com"
        assert browser_validated.timeout == 5000
        assert browser_validated.screenshot is True

        # Test 2: Search with aliases
        search_raw = {"q": "machine learning", "limit": 50}

        search_canonical = canonicalizer.canonicalize("search", search_raw)
        search_validated = SearchArgs(**search_canonical)

        assert search_validated.query == "machine learning"
        assert search_validated.max_results == 50

        # Test 3: Invalid args rejected by Pydantic
        invalid_browser = {
            "uri": "https://example.com",
            "timeout_ms": -100,  # Invalid (negative)
        }

        invalid_canonical = canonicalizer.canonicalize("browser", invalid_browser)

        with pytest.raises(ValidationError) as exc_info:
            BrowserArgs(**invalid_canonical)

        # Verify Pydantic caught the validation error
        error_str = str(exc_info.value)
        assert "timeout" in error_str

    @pytest.mark.asyncio
    async def test_case_sensitivity(self, canonicalizer):
        """E2E: Aliases are case-sensitive."""
        # Uppercase alias not recognized
        args_upper = {"URI": "https://example.com"}
        canonical_upper = canonicalizer.canonicalize("browser", args_upper)

        # Should NOT be canonicalized (case mismatch)
        assert "URI" in canonical_upper
        assert "url" not in canonical_upper

        # Lowercase alias recognized
        args_lower = {"uri": "https://example.com"}
        canonical_lower = canonicalizer.canonicalize("browser", args_lower)

        # Should be canonicalized
        assert "url" in canonical_lower
        assert "uri" not in canonical_lower

    @pytest.mark.asyncio
    async def test_complex_nested_values(self, canonicalizer):
        """E2E: Canonicalization preserves complex nested values."""
        # Args with nested objects and arrays
        complex_args = {
            "uri": "https://example.com",
            "headers": {
                "Authorization": "Bearer token123",
                "Content-Type": "application/json",
            },
            "body": {"user": {"name": "test", "roles": ["admin", "user"]}},
        }

        canonical = canonicalizer.canonicalize("browser", complex_args)

        # Alias mapped
        assert "url" in canonical
        assert canonical["url"] == "https://example.com"

        # Nested structures preserved exactly
        assert canonical["headers"]["Authorization"] == "Bearer token123"
        assert canonical["body"]["user"]["name"] == "test"
        assert canonical["body"]["user"]["roles"] == ["admin", "user"]

    @pytest.mark.asyncio
    async def test_rejection_reason_accuracy(self, canonicalizer):
        """E2E: Rejection reasons accurately describe the problem."""
        # Test unknown field rejection
        args = {"url": "https://test.com", "bad_field_1": "value1", "bad_field_2": "value2"}

        canonical = canonicalizer.canonicalize("browser", args)
        known_fields = {"url", "timeout"}

        valid, unknown = canonicalizer.validate_no_unknown_fields("browser", canonical, known_fields)

        # Verify all unknown fields listed
        assert valid is False
        assert set(unknown) == {"bad_field_1", "bad_field_2"}

        # Verify rejection metric tracks count
        rejection_count = agent_tool_args_rejected.get({"tool_name": "browser", "rejection_reason": "unknown_field"})
        assert rejection_count > 0
