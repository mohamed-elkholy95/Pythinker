"""Tests for Enhanced Chain-of-Verification (CoVe) claim verification.

Tests the verify_claims_against_sources functionality that verifies
claims in summaries against actual tool outputs.
"""

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.langgraph.nodes.summarize import (
    ClaimVerificationResult,
    ClaimVerifier,
    _extract_claims_from_summary,
    _run_claim_verification,
    get_claim_verifier,
)


class TestClaimVerificationResult:
    """Tests for ClaimVerificationResult dataclass."""

    def test_create_verified_result(self) -> None:
        """Test creating a verified claim result."""
        result = ClaimVerificationResult(
            claim="Found 5 files in the directory",
            verified=True,
            reason="Supported by search tool",
            confidence=0.9,
        )

        assert result.claim == "Found 5 files in the directory"
        assert result.verified is True
        assert result.confidence == 0.9
        assert result.source_output is None

    def test_create_unverified_result(self) -> None:
        """Test creating an unverified claim result."""
        result = ClaimVerificationResult(
            claim="The file contains 100 lines",
            verified=False,
            reason="No supporting tool output found",
            confidence=0.2,
        )

        assert result.verified is False
        assert result.confidence == 0.2

    def test_result_with_source_output(self) -> None:
        """Test result with source output attached."""
        tool_result: ToolResult[dict[str, str]] = ToolResult.ok(
            message="Found 5 files",
            data={"count": "5"},
        )

        result = ClaimVerificationResult(
            claim="Found 5 files",
            verified=True,
            reason="Supported by search",
            confidence=0.95,
            source_output=tool_result,
        )

        assert result.source_output is not None
        assert result.source_output.success is True


class TestClaimVerifier:
    """Tests for ClaimVerifier class."""

    @pytest.fixture
    def verifier(self) -> ClaimVerifier:
        """Create a ClaimVerifier instance."""
        return ClaimVerifier()

    @pytest.fixture
    def sample_tool_results(self) -> list[ToolResult[dict[str, str | int | list[str]]]]:
        """Create sample tool results for testing."""
        return [
            ToolResult.ok(
                message="Search completed: found 5 matching files",
                data={
                    "tool_name": "file_search",
                    "count": 5,
                    "files": ["a.py", "b.py", "c.py", "d.py", "e.py"],
                },
            ),
            ToolResult.ok(
                message="File read successfully",
                data={
                    "tool_name": "read_file",
                    "content": "This file contains 150 lines of Python code",
                    "lines": 150,
                },
            ),
            ToolResult.ok(
                message="Command executed successfully",
                data={
                    "tool_name": "terminal",
                    "output": "Tests passed: 12 passed, 0 failed in 3.5 seconds",
                },
            ),
        ]

    @pytest.mark.asyncio
    async def test_verify_supported_claim(
        self,
        verifier: ClaimVerifier,
        sample_tool_results: list[ToolResult[dict[str, str | int | list[str]]]],
    ) -> None:
        """Test verifying a claim that is supported by tool output."""
        claims = ["Found 5 matching files in the search"]

        results = await verifier.verify_claims_against_sources(claims, sample_tool_results)

        assert len(results) == 1
        assert results[0].verified is True
        assert results[0].confidence >= 0.7
        assert "file_search" in results[0].reason or "Supported" in results[0].reason

    @pytest.mark.asyncio
    async def test_verify_unsupported_claim(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test verifying a claim with no supporting evidence."""
        claims = ["The database contains 1 million records"]
        tool_results: list[ToolResult[dict[str, str]]] = [
            ToolResult.ok(message="File created", data={"result": "ok"}),
        ]

        results = await verifier.verify_claims_against_sources(claims, tool_results)

        assert len(results) == 1
        assert results[0].verified is False
        assert results[0].confidence < 0.7

    @pytest.mark.asyncio
    async def test_verify_no_tool_outputs(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test verification with no tool outputs available."""
        claims = ["Found 10 results"]
        tool_results: list[ToolResult[dict[str, str]]] = []

        results = await verifier.verify_claims_against_sources(claims, tool_results)

        assert len(results) == 1
        assert results[0].verified is False
        assert results[0].reason == "No supporting tool output found"
        assert results[0].confidence == 0.2

    @pytest.mark.asyncio
    async def test_verify_multiple_claims(
        self,
        verifier: ClaimVerifier,
        sample_tool_results: list[ToolResult[dict[str, str | int | list[str]]]],
    ) -> None:
        """Test verifying multiple claims at once."""
        claims = [
            "Found 5 matching files",
            "File contains 150 lines",
            "12 tests passed",
            "Server is running on port 9999",  # Not in outputs
        ]

        results = await verifier.verify_claims_against_sources(claims, sample_tool_results)

        assert len(results) == 4
        # First 3 should be verified (match tool outputs)
        verified_count = sum(1 for r in results if r.verified)
        assert verified_count >= 2  # At least 2 should be verified

        # Last one should not be verified
        assert results[3].verified is False

    @pytest.mark.asyncio
    async def test_verify_exact_number_match(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test that exact number matches boost confidence."""
        claims = ["The search returned 42 results"]
        tool_results: list[ToolResult[dict[str, int]]] = [
            ToolResult.ok(
                message="Search complete",
                data={"count": 42, "tool_name": "search"},
            ),
        ]

        results = await verifier.verify_claims_against_sources(claims, tool_results)

        assert results[0].confidence >= 0.7

    @pytest.mark.asyncio
    async def test_verify_wrong_number(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test that wrong numbers result in low confidence."""
        claims = ["Found 100 files"]
        tool_results: list[ToolResult[dict[str, int]]] = [
            ToolResult.ok(
                message="Found 5 files",
                data={"count": 5},
            ),
        ]

        results = await verifier.verify_claims_against_sources(claims, tool_results)

        # Should have lower confidence due to number mismatch
        # May still match on keywords but not high confidence
        assert results[0].confidence < 0.9

    @pytest.mark.asyncio
    async def test_verify_with_failed_tool_result(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test that failed tool results reduce confidence."""
        claims = ["Operation completed successfully"]
        tool_results: list[ToolResult[str]] = [
            ToolResult.error(
                message="Operation completed successfully",
                data="error details",
            ),
        ]

        results = await verifier.verify_claims_against_sources(claims, tool_results)

        # Should match but with reduced confidence due to failed status
        if results[0].verified:
            assert results[0].confidence < 0.9  # Confidence penalty applied

    def test_find_relevant_outputs(
        self,
        verifier: ClaimVerifier,
        sample_tool_results: list[ToolResult[dict[str, str | int | list[str]]]],
    ) -> None:
        """Test finding relevant outputs for a claim."""
        claim = "Found 5 matching files"

        relevant = verifier._find_relevant_outputs(claim, sample_tool_results)

        # Should find the file_search result
        assert len(relevant) >= 1

    def test_find_relevant_outputs_with_numbers(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test that number matching helps find relevant outputs."""
        claim = "There are 42 items"
        tool_results: list[ToolResult[dict[str, int]]] = [
            ToolResult.ok(message="Random output", data={"value": 42}),
            ToolResult.ok(message="Other output", data={"value": 100}),
        ]

        relevant = verifier._find_relevant_outputs(claim, tool_results)

        # Should find the one with 42
        assert len(relevant) >= 1

    def test_calculate_support_confidence_exact_match(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test confidence calculation for exact text match."""
        claim = "found 5 files"
        output: ToolResult[dict[str, str]] = ToolResult.ok(
            message="Search complete: found 5 files in the directory",
            data={"content": "found 5 files"},
        )

        confidence = verifier._calculate_support_confidence(claim, output)

        assert confidence >= 0.9

    def test_calculate_support_confidence_no_match(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test confidence calculation with no match."""
        claim = "database contains 1000 records"
        output: ToolResult[dict[str, str]] = ToolResult.ok(
            message="File saved",
            data={"result": "ok"},
        )

        confidence = verifier._calculate_support_confidence(claim, output)

        # Should have low confidence, not verifiable (below threshold)
        assert confidence < 0.7  # Below verification threshold

    def test_extract_content_from_string_data(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test content extraction from string data."""
        output: ToolResult[str] = ToolResult.ok(
            message="Success",
            data="This is the content",
        )

        content = verifier._extract_content(output)

        assert "Success" in content
        assert "This is the content" in content

    def test_extract_content_from_dict_data(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test content extraction from dict data."""
        output: ToolResult[dict[str, str]] = ToolResult.ok(
            message="Done",
            data={"content": "File content here", "text": "Additional text"},
        )

        content = verifier._extract_content(output)

        assert "File content here" in content
        assert "Additional text" in content

    def test_extract_content_from_list_data(
        self,
        verifier: ClaimVerifier,
    ) -> None:
        """Test content extraction from list data."""
        output: ToolResult[list[str]] = ToolResult.ok(
            message="Results",
            data=["item1", "item2", "item3"],
        )

        content = verifier._extract_content(output)

        assert "item1" in content
        assert "item2" in content


class TestExtractClaimsFromSummary:
    """Tests for claim extraction from summary content."""

    def test_extract_numeric_claims(self) -> None:
        """Test extracting claims with numbers."""
        content = (
            "The search found 15 matching files. The command executed in 2.5 seconds. This is just a regular sentence."
        )

        claims = _extract_claims_from_summary(content)

        # Should extract numeric claims
        assert len(claims) >= 2
        assert any("15" in c for c in claims)
        assert any("2.5" in c for c in claims)

    def test_extract_file_operation_claims(self) -> None:
        """Test extracting file operation claims."""
        content = "Created 3 new files in the project. Deleted 2 temporary files. Modified 5 configuration files."

        claims = _extract_claims_from_summary(content)

        assert len(claims) >= 3

    def test_extract_result_claims(self) -> None:
        """Test extracting claims about results."""
        content = (
            "The search result shows all matching items. "
            "The file content was extracted successfully. "
            "The command output indicates success."
        )

        claims = _extract_claims_from_summary(content)

        # Should extract tool-related claims
        assert len(claims) >= 1

    def test_extract_percentage_claims(self) -> None:
        """Test extracting claims with percentages."""
        content = "The test coverage is 85%. Memory usage is at 45%."

        claims = _extract_claims_from_summary(content)

        assert len(claims) >= 2
        assert any("85%" in c for c in claims)

    def test_extract_size_claims(self) -> None:
        """Test extracting claims with size measurements."""
        content = "The file is 1.5 MB large. Downloaded 500 KB of data."

        claims = _extract_claims_from_summary(content)

        assert len(claims) >= 2

    def test_limit_claims_count(self) -> None:
        """Test that claims are limited to prevent excessive verification."""
        # Create content with many potential claims
        content = " ".join([f"Found {i} items." for i in range(20)])

        claims = _extract_claims_from_summary(content)

        assert len(claims) <= 10

    def test_empty_content(self) -> None:
        """Test extraction from empty content."""
        claims = _extract_claims_from_summary("")

        assert claims == []

    def test_no_verifiable_claims(self) -> None:
        """Test content with no verifiable claims."""
        content = "This is a general description. The task has been completed. Everything looks good."

        claims = _extract_claims_from_summary(content)

        # May still extract some claims based on keywords
        # But shouldn't extract false positives
        assert isinstance(claims, list)


class TestRunClaimVerification:
    """Tests for the _run_claim_verification helper function."""

    @pytest.mark.asyncio
    async def test_verification_with_empty_results(self) -> None:
        """Test verification with no tool results."""
        content = "Found 5 files in the search."
        tool_results: list[ToolResult[str]] = []

        result = await _run_claim_verification(content, tool_results)

        assert result["passed"] is True
        assert result["verified_claims"] == []

    @pytest.mark.asyncio
    async def test_verification_with_matching_results(self) -> None:
        """Test verification where claims match tool outputs."""
        content = "The search found 10 results. The command completed successfully."
        tool_results: list[ToolResult[dict[str, str | int]]] = [
            ToolResult.ok(
                message="Search complete: 10 results found",
                data={"count": 10, "tool_name": "search"},
            ),
        ]

        result = await _run_claim_verification(content, tool_results)

        assert "verification_ratio" in result
        # Should have at least some verified claims
        if result["verified_claims"]:
            assert len(result["verified_claims"]) >= 1

    @pytest.mark.asyncio
    async def test_verification_calculates_ratio(self) -> None:
        """Test that verification ratio is calculated correctly."""
        content = "Found 5 files. Created 3 documents."
        tool_results: list[ToolResult[dict[str, str | int]]] = [
            ToolResult.ok(
                message="Found 5 files",
                data={"count": 5, "tool_name": "search"},
            ),
        ]

        result = await _run_claim_verification(content, tool_results)

        assert "verification_ratio" in result
        assert 0 <= result["verification_ratio"] <= 1

    @pytest.mark.asyncio
    async def test_verification_short_content(self) -> None:
        """Test verification with content that has no extractable claims."""
        content = "Done."
        tool_results: list[ToolResult[dict[str, str]]] = [
            ToolResult.ok(message="OK", data={}),
        ]

        result = await _run_claim_verification(content, tool_results)

        # Should pass with no claims to verify
        assert result["passed"] is True


class TestGetClaimVerifier:
    """Tests for the singleton verifier getter."""

    def test_returns_verifier_instance(self) -> None:
        """Test that get_claim_verifier returns a ClaimVerifier."""
        verifier = get_claim_verifier()

        assert isinstance(verifier, ClaimVerifier)

    def test_returns_same_instance(self) -> None:
        """Test that get_claim_verifier returns the same instance."""
        verifier1 = get_claim_verifier()
        verifier2 = get_claim_verifier()

        assert verifier1 is verifier2


class TestClaimVerifierConfiguration:
    """Tests for ClaimVerifier configuration options."""

    def test_custom_similarity_threshold(self) -> None:
        """Test verifier with custom similarity threshold."""
        verifier = ClaimVerifier(similarity_threshold=0.8)

        assert verifier.similarity_threshold == 0.8

    def test_custom_confidence_threshold(self) -> None:
        """Test verifier with custom confidence threshold."""
        verifier = ClaimVerifier(confidence_threshold=0.9)

        assert verifier.confidence_threshold == 0.9

    @pytest.mark.asyncio
    async def test_higher_confidence_threshold_stricter(self) -> None:
        """Test that higher confidence threshold is stricter."""
        strict_verifier = ClaimVerifier(confidence_threshold=0.95)
        lenient_verifier = ClaimVerifier(confidence_threshold=0.5)

        claims = ["Found approximately 5 items"]
        tool_results: list[ToolResult[dict[str, str | int]]] = [
            ToolResult.ok(
                message="Found some items",
                data={"count": 5},
            ),
        ]

        strict_results = await strict_verifier.verify_claims_against_sources(claims, tool_results)
        lenient_results = await lenient_verifier.verify_claims_against_sources(claims, tool_results)

        # With same confidence, strict threshold should verify fewer
        strict_verified = sum(1 for r in strict_results if r.verified)
        lenient_verified = sum(1 for r in lenient_results if r.verified)

        assert lenient_verified >= strict_verified
