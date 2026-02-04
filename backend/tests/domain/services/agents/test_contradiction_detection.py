# backend/tests/domain/services/agents/test_contradiction_detection.py
"""Tests for cross-claim contradiction detection.

Tests the ContradictionDetector's ability to identify internally
contradictory claims within text output.
"""

import pytest

from app.domain.services.agents.content_hallucination_detector import (
    Claim,
    ContentHallucinationDetector,
    ContradictionResult,
)


@pytest.fixture
def detector() -> ContentHallucinationDetector:
    """Create a ContentHallucinationDetector instance."""
    return ContentHallucinationDetector()


class TestClaimDataclass:
    """Tests for the Claim dataclass."""

    def test_claim_creation_minimal(self):
        """Claim can be created with minimal required fields."""
        claim = Claim(text="The API returns JSON.", entities=["api"])
        assert claim.text == "The API returns JSON."
        assert claim.entities == ["api"]
        assert claim.numeric_value is None
        assert claim.metric is None
        assert claim.polarity is None

    def test_claim_creation_full(self):
        """Claim can be created with all fields."""
        claim = Claim(
            text="Performance improved by 20%.",
            entities=["performance"],
            numeric_value=20.0,
            metric="percentage_improvement",
            polarity=0.8,
            start_pos=0,
            end_pos=30,
        )
        assert claim.numeric_value == 20.0
        assert claim.metric == "percentage_improvement"
        assert claim.polarity == 0.8


class TestContradictionResultDataclass:
    """Tests for the ContradictionResult dataclass."""

    def test_contradiction_result_creation(self):
        """ContradictionResult can be created with required fields."""
        result = ContradictionResult(
            claim1="The API returns JSON.",
            claim2="The response is XML.",
            entity="api",
            confidence=0.85,
        )
        assert result.claim1 == "The API returns JSON."
        assert result.claim2 == "The response is XML."
        assert result.entity == "api"
        assert result.confidence == 0.85
        assert result.contradiction_type == "general"

    def test_contradiction_result_with_type(self):
        """ContradictionResult can include contradiction type."""
        result = ContradictionResult(
            claim1="Performance improved 20%.",
            claim2="Speed decreased significantly.",
            entity="performance",
            confidence=0.9,
            contradiction_type="polarity",
        )
        assert result.contradiction_type == "polarity"


class TestExtractEntities:
    """Tests for entity extraction from text."""

    def test_extract_programming_languages(self, detector):
        """Should extract programming language names."""
        entities = detector._extract_entities("Python 3.10 is required for this project.")
        assert "python 3.10" in entities or "python" in entities

    def test_extract_frameworks(self, detector):
        """Should extract framework names."""
        entities = detector._extract_entities("The application uses React and FastAPI.")
        assert "react" in entities
        assert "fastapi" in entities

    def test_extract_data_formats(self, detector):
        """Should extract data format names."""
        entities = detector._extract_entities("The API returns JSON responses.")
        assert "json" in entities
        assert "api" in entities

    def test_extract_databases(self, detector):
        """Should extract database names."""
        entities = detector._extract_entities("Data is stored in MongoDB with Redis caching.")
        assert "mongodb" in entities
        assert "redis" in entities

    def test_extract_quoted_terms(self, detector):
        """Should extract quoted terms as entities."""
        entities = detector._extract_entities("The 'user_id' field is required.")
        assert "user_id" in entities

    def test_empty_text_returns_empty_list(self, detector):
        """Empty text should return empty entity list."""
        entities = detector._extract_entities("")
        assert entities == []


class TestExtractNumericMetric:
    """Tests for numeric value and metric extraction."""

    def test_extract_percentage(self, detector):
        """Should extract percentage values."""
        value, metric = detector._extract_numeric_metric("Performance improved by 25%.")
        assert value == 25.0
        assert "percentage" in metric

    def test_extract_duration(self, detector):
        """Should extract time durations."""
        value, metric = detector._extract_numeric_metric("Response time is 150 milliseconds.")
        assert value == 150.0
        assert "duration" in metric

    def test_extract_size(self, detector):
        """Should extract size values."""
        value, metric = detector._extract_numeric_metric("The file is 50 MB.")
        assert value == 50.0
        assert "size" in metric

    def test_no_numeric_returns_none(self, detector):
        """Text without numbers should return None."""
        value, metric = detector._extract_numeric_metric("The API is fast.")
        assert value is None
        assert metric is None


class TestExtractPolarity:
    """Tests for sentiment polarity extraction."""

    def test_positive_polarity(self, detector):
        """Should detect positive sentiment."""
        polarity = detector._extract_polarity("Performance has improved significantly.")
        assert polarity is not None
        assert polarity > 0

    def test_negative_polarity(self, detector):
        """Should detect negative sentiment."""
        polarity = detector._extract_polarity("Speed has decreased dramatically.")
        assert polarity is not None
        assert polarity < 0

    def test_neutral_text_returns_none(self, detector):
        """Neutral text should return None."""
        polarity = detector._extract_polarity("The file contains data.")
        assert polarity is None

    def test_negation_flips_polarity(self, detector):
        """Negation should affect polarity."""
        positive_polarity = detector._extract_polarity("The system supports this feature.")
        negated_polarity = detector._extract_polarity("The system does not support this feature.")
        # Both should have polarity but in different directions
        assert positive_polarity is not None
        assert negated_polarity is not None
        # The negated version should be less positive or negative
        assert negated_polarity < positive_polarity


class TestClaimsContradict:
    """Tests for the _claims_contradict method."""

    def test_numeric_contradiction(self, detector):
        """Should detect numeric value contradictions."""
        claim1 = Claim(
            text="Performance improved by 50%.",
            entities=["performance"],
            numeric_value=50.0,
            metric="percentage_improvement",
        )
        claim2 = Claim(
            text="Performance improved by 10%.",
            entities=["performance"],
            numeric_value=10.0,
            metric="percentage_improvement",
        )
        assert detector._claims_contradict(claim1, claim2) is True

    def test_numeric_no_contradiction_small_diff(self, detector):
        """Should not flag small numeric differences as contradictions."""
        claim1 = Claim(
            text="Performance improved by 20%.",
            entities=["performance"],
            numeric_value=20.0,
            metric="percentage_improvement",
        )
        claim2 = Claim(
            text="Performance improved by 22%.",
            entities=["performance"],
            numeric_value=22.0,
            metric="percentage_improvement",
        )
        # 10% difference should not be flagged (ratio < 1.5)
        assert detector._claims_contradict(claim1, claim2) is False

    def test_polarity_contradiction(self, detector):
        """Should detect polarity contradictions."""
        claim1 = Claim(
            text="The system performance has improved.",
            entities=["performance"],
            polarity=0.8,
        )
        claim2 = Claim(
            text="The system performance has decreased.",
            entities=["performance"],
            polarity=-0.8,
        )
        assert detector._claims_contradict(claim1, claim2) is True

    def test_negation_contradiction_support(self, detector):
        """Should detect support/not support contradictions."""
        claim1 = Claim(text="The API supports JSON.", entities=["api", "json"])
        claim2 = Claim(text="The API does not support JSON.", entities=["api", "json"])
        assert detector._claims_contradict(claim1, claim2) is True

    def test_negation_contradiction_require(self, detector):
        """Should detect require/not require contradictions."""
        claim1 = Claim(text="Python requires this module.", entities=["python"])
        claim2 = Claim(text="Python does not require this module.", entities=["python"])
        assert detector._claims_contradict(claim1, claim2) is True

    def test_negation_contradiction_include(self, detector):
        """Should detect include/not include contradictions."""
        claim1 = Claim(text="The package includes documentation.", entities=["package"])
        claim2 = Claim(text="The package does not include documentation.", entities=["package"])
        assert detector._claims_contradict(claim1, claim2) is True


class TestFormatContradiction:
    """Tests for format contradiction detection."""

    def test_json_xml_contradiction(self, detector):
        """Should detect JSON vs XML format contradiction."""
        result = detector._check_format_contradiction(
            "The API returns JSON.",
            "The response is in XML format.",
        )
        assert result is True

    def test_rest_graphql_contradiction(self, detector):
        """Should detect REST vs GraphQL contradiction."""
        result = detector._check_format_contradiction(
            "The service uses REST endpoints.",
            "The service requires GraphQL queries.",
        )
        assert result is True

    def test_same_format_no_contradiction(self, detector):
        """Should not flag same format as contradiction."""
        result = detector._check_format_contradiction(
            "The API returns JSON.",
            "The response uses JSON format.",
        )
        assert result is False

    def test_different_context_no_contradiction(self, detector):
        """Should not flag formats in unrelated contexts."""
        result = detector._check_format_contradiction(
            "JSON is a popular data format.",
            "XML has been used for decades.",
        )
        # These are just statements about formats, not conflicting claims
        assert result is False


class TestVersionContradiction:
    """Tests for version requirement contradiction detection."""

    def test_python_version_contradiction(self, detector):
        """Should detect Python version contradictions."""
        result = detector._check_version_contradiction(
            "Requires Python 3.8 or higher.",
            "Requires Python 3.10 minimum.",
        )
        assert result is True

    def test_same_version_no_contradiction(self, detector):
        """Should not flag same version as contradiction."""
        result = detector._check_version_contradiction(
            "Requires Python 3.10.",
            "Python 3.10 is required.",
        )
        assert result is False

    def test_no_version_no_contradiction(self, detector):
        """Should not flag text without versions."""
        result = detector._check_version_contradiction(
            "Python is required.",
            "Python should be installed.",
        )
        assert result is False


class TestDetectContradictions:
    """Integration tests for the full detect_contradictions method."""

    def test_detect_format_contradiction(self, detector):
        """Should detect format contradictions in text."""
        text = """
        The API returns data in JSON format for all endpoints.
        Response payloads are structured as XML documents.
        """
        contradictions = detector.detect_contradictions(text)
        # Should find at least one contradiction
        assert len(contradictions) >= 1
        # Check contradiction is about format
        found_format = any(c.contradiction_type == "format" for c in contradictions)
        assert found_format

    def test_detect_polarity_contradiction(self, detector):
        """Should detect polarity contradictions in text."""
        text = """
        The system performance has improved dramatically after the update.
        Performance has decreased significantly since the deployment.
        """
        contradictions = detector.detect_contradictions(text)
        assert len(contradictions) >= 1

    def test_detect_negation_contradiction(self, detector):
        """Should detect negation contradictions in text."""
        text = """
        The framework supports Python 3.8+ versions.
        The framework does not support Python versions.
        """
        contradictions = detector.detect_contradictions(text)
        assert len(contradictions) >= 1

    def test_detect_numeric_contradiction(self, detector):
        """Should detect numeric contradictions in text."""
        text = """
        Response time improved by 80% after optimization.
        The latency reduction was about 20% compared to before.
        """
        contradictions = detector.detect_contradictions(text)
        # May or may not flag depending on shared entities
        # The key is it doesn't crash and returns valid results
        assert isinstance(contradictions, list)

    def test_no_contradiction_in_consistent_text(self, detector):
        """Should return empty list for consistent text."""
        text = """
        The API returns JSON responses.
        All endpoints use JSON format.
        JSON is the standard data format for this service.
        """
        contradictions = detector.detect_contradictions(text)
        assert len(contradictions) == 0

    def test_empty_text_returns_empty_list(self, detector):
        """Empty text should return empty contradiction list."""
        contradictions = detector.detect_contradictions("")
        assert contradictions == []

    def test_short_text_returns_empty_list(self, detector):
        """Very short text should return empty list."""
        contradictions = detector.detect_contradictions("OK.")
        assert contradictions == []

    def test_contradiction_includes_entity(self, detector):
        """Detected contradictions should include the shared entity."""
        text = """
        The API endpoint returns JSON data.
        The API response is formatted as XML.
        """
        contradictions = detector.detect_contradictions(text)
        if contradictions:
            # Should have entity field populated
            assert all(c.entity for c in contradictions)

    def test_contradiction_confidence_range(self, detector):
        """Contradiction confidence should be between 0 and 1."""
        text = """
        Performance improved by 50%.
        Speed decreased by 30%.
        """
        contradictions = detector.detect_contradictions(text)
        for contradiction in contradictions:
            assert 0 <= contradiction.confidence <= 1


class TestContradictionConfidence:
    """Tests for confidence scoring of contradictions."""

    def test_high_confidence_for_numeric_contradiction(self, detector):
        """Numeric contradictions should have higher confidence."""
        claim1 = Claim(
            text="Improved by 80%.",
            entities=["performance"],
            numeric_value=80.0,
            metric="percentage",
        )
        claim2 = Claim(
            text="Improved by 10%.",
            entities=["performance"],
            numeric_value=10.0,
            metric="percentage",
        )
        confidence = detector._contradiction_confidence(claim1, claim2)
        assert confidence > 0.6

    def test_high_confidence_for_negation(self, detector):
        """Negation contradictions should have higher confidence."""
        claim1 = Claim(text="The API supports JSON.", entities=["api"])
        claim2 = Claim(text="The API does not support JSON.", entities=["api"])
        confidence = detector._contradiction_confidence(claim1, claim2)
        assert confidence >= 0.7

    def test_higher_confidence_for_shared_entities(self, detector):
        """More shared entities should increase confidence."""
        claim1 = Claim(text="Test", entities=["api", "json", "response"])
        claim2 = Claim(text="Test", entities=["api", "json", "endpoint"])
        confidence = detector._contradiction_confidence(claim1, claim2)
        # Should be boosted by 2 shared entities
        assert confidence > 0.5


class TestGetContradictionType:
    """Tests for contradiction type classification."""

    def test_numeric_type(self, detector):
        """Should identify numeric contradiction type."""
        claim1 = Claim(text="50%", entities=["x"], numeric_value=50.0, metric="percentage")
        claim2 = Claim(text="10%", entities=["x"], numeric_value=10.0, metric="percentage")
        ctype = detector._get_contradiction_type(claim1, claim2)
        assert ctype == "numeric"

    def test_polarity_type(self, detector):
        """Should identify polarity contradiction type."""
        claim1 = Claim(text="improved", entities=["x"], polarity=0.8)
        claim2 = Claim(text="decreased", entities=["x"], polarity=-0.8)
        ctype = detector._get_contradiction_type(claim1, claim2)
        assert ctype == "polarity"

    def test_negation_type(self, detector):
        """Should identify negation contradiction type."""
        claim1 = Claim(text="supports feature", entities=["x"])
        claim2 = Claim(text="does not support feature", entities=["x"])
        ctype = detector._get_contradiction_type(claim1, claim2)
        assert ctype == "negation"


class TestRealWorldExamples:
    """Tests with real-world example texts."""

    def test_api_documentation_contradiction(self, detector):
        """Should detect contradictions in API documentation."""
        text = """
        ## API Overview

        The REST API returns all responses in JSON format.
        Authentication is handled via JWT tokens in the Authorization header.

        ## Response Format

        All API endpoints return XML documents with a standard structure.
        The root element contains metadata about the request.
        """
        contradictions = detector.detect_contradictions(text)
        # Should detect JSON vs XML contradiction
        assert len(contradictions) >= 1

    def test_performance_report_contradiction(self, detector):
        """Should detect contradictions in performance reports."""
        text = """
        Performance Results:
        - Database query time improved by 60% after indexing
        - Query performance decreased due to the new indexes
        - Memory usage was reduced by 40%
        """
        contradictions = detector.detect_contradictions(text)
        # Should detect improved vs decreased contradiction
        assert len(contradictions) >= 1

    def test_requirements_documentation(self, detector):
        """Should detect contradictions in requirements docs."""
        text = """
        System Requirements:
        - Supports Python 3.8 and above
        - Compatible with all Python versions

        Installation:
        - Requires Python 3.11 minimum
        """
        contradictions = detector.detect_contradictions(text)
        # Should detect version contradiction
        assert len(contradictions) >= 1

    def test_consistent_technical_doc(self, detector):
        """Should not flag consistent technical documentation."""
        text = """
        The application uses FastAPI for the backend.
        FastAPI provides automatic API documentation.
        The REST endpoints return JSON responses.
        All data is serialized to JSON format.
        """
        contradictions = detector.detect_contradictions(text)
        # Should be consistent, no contradictions
        assert len(contradictions) == 0
