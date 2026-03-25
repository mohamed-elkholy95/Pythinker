"""Tests for GroundingValidator and related models.

Tests cover:
- GroundingLevel enum
- Claim, NumericClaim, EntityClaim dataclasses
- GroundingResult and EnhancedGroundingResult properties
- GroundingValidator claim extraction, scoring, and validation
- EnhancedGroundingValidator numeric/entity extraction and verification
"""

from app.domain.services.agents.grounding_validator import (
    Claim,
    EnhancedGroundingResult,
    EnhancedGroundingValidator,
    EntityClaim,
    GroundingLevel,
    GroundingResult,
    GroundingValidator,
    NumericClaim,
)

# ── GroundingLevel Enum ──────────────────────────────────────────────


class TestGroundingLevel:
    def test_fully_grounded_value(self):
        assert GroundingLevel.FULLY_GROUNDED == "fully_grounded"

    def test_partially_grounded_value(self):
        assert GroundingLevel.PARTIALLY_GROUNDED == "partially_grounded"

    def test_weakly_grounded_value(self):
        assert GroundingLevel.WEAKLY_GROUNDED == "weakly_grounded"

    def test_ungrounded_value(self):
        assert GroundingLevel.UNGROUNDED == "ungrounded"

    def test_all_members(self):
        assert len(GroundingLevel) == 4


# ── Claim Dataclass ──────────────────────────────────────────────────


class TestClaim:
    def test_construction_minimal(self):
        c = Claim(text="Python is fast.")
        assert c.text == "Python is fast."
        assert c.source_support is None
        assert c.grounding_score == 0.0
        assert c.is_factual is True

    def test_construction_full(self):
        c = Claim(text="X", source_support="src", grounding_score=0.8, is_factual=False)
        assert c.source_support == "src"
        assert c.grounding_score == 0.8
        assert c.is_factual is False


# ── NumericClaim Dataclass ───────────────────────────────────────────


class TestNumericClaim:
    def test_construction_minimal(self):
        nc = NumericClaim(text="Score is 92%.", value=92.0)
        assert nc.value == 92.0
        assert nc.unit == ""
        assert nc.entity is None
        assert nc.metric is None
        assert nc.is_verified is False

    def test_construction_full(self):
        nc = NumericClaim(
            text="Claude scores 92% on MMLU.",
            value=92.0,
            unit="%",
            entity="Claude",
            metric="MMLU",
            context_window="Claude scores 92% on MMLU.",
            is_verified=True,
            verification_source="source text",
            verification_excerpt="92%",
        )
        assert nc.entity == "Claude"
        assert nc.metric == "MMLU"
        assert nc.is_verified is True


# ── EntityClaim Dataclass ────────────────────────────────────────────


class TestEntityClaim:
    def test_construction_minimal(self):
        ec = EntityClaim(text="OpenAI released GPT-5.", entity="OpenAI", claim_about="released GPT-5.")
        assert ec.entity == "OpenAI"
        assert ec.entity_type == "unknown"
        assert ec.is_verified is False

    def test_construction_full(self):
        ec = EntityClaim(
            text="OpenAI released GPT-5.",
            entity="OpenAI",
            claim_about="released GPT-5.",
            entity_type="company",
            is_verified=True,
            verification_source="news article",
        )
        assert ec.entity_type == "company"
        assert ec.is_verified is True


# ── GroundingResult ──────────────────────────────────────────────────


class TestGroundingResult:
    def test_is_acceptable_fully_grounded(self):
        r = GroundingResult(
            overall_score=0.9,
            level=GroundingLevel.FULLY_GROUNDED,
            claims=[],
            ungrounded_claims=[],
            grounded_claims=["c1"],
        )
        assert r.is_acceptable is True

    def test_is_acceptable_partially_grounded(self):
        r = GroundingResult(
            overall_score=0.6,
            level=GroundingLevel.PARTIALLY_GROUNDED,
            claims=[],
            ungrounded_claims=[],
            grounded_claims=["c1"],
        )
        assert r.is_acceptable is True

    def test_not_acceptable_weakly_grounded(self):
        r = GroundingResult(
            overall_score=0.3,
            level=GroundingLevel.WEAKLY_GROUNDED,
            claims=[],
            ungrounded_claims=["c1"],
            grounded_claims=[],
        )
        assert r.is_acceptable is False

    def test_needs_revision_weakly(self):
        r = GroundingResult(
            overall_score=0.3,
            level=GroundingLevel.WEAKLY_GROUNDED,
            claims=[],
            ungrounded_claims=["c1"],
            grounded_claims=[],
        )
        assert r.needs_revision is True

    def test_needs_revision_ungrounded(self):
        r = GroundingResult(
            overall_score=0.1,
            level=GroundingLevel.UNGROUNDED,
            claims=[],
            ungrounded_claims=["c1"],
            grounded_claims=[],
        )
        assert r.needs_revision is True

    def test_no_revision_fully_grounded(self):
        r = GroundingResult(
            overall_score=0.9,
            level=GroundingLevel.FULLY_GROUNDED,
            claims=[],
            ungrounded_claims=[],
            grounded_claims=["c1"],
        )
        assert r.needs_revision is False

    def test_get_revision_guidance_with_claims(self):
        r = GroundingResult(
            overall_score=0.2,
            level=GroundingLevel.UNGROUNDED,
            claims=[],
            ungrounded_claims=["Claim A", "Claim B"],
            grounded_claims=[],
        )
        guidance = r.get_revision_guidance()
        assert "Claim A" in guidance
        assert "Claim B" in guidance
        assert "Remove or qualify" in guidance

    def test_get_revision_guidance_empty(self):
        r = GroundingResult(
            overall_score=0.9,
            level=GroundingLevel.FULLY_GROUNDED,
            claims=[],
            ungrounded_claims=[],
            grounded_claims=["c1"],
        )
        assert r.get_revision_guidance() == ""

    def test_get_revision_guidance_limits_to_5(self):
        r = GroundingResult(
            overall_score=0.1,
            level=GroundingLevel.UNGROUNDED,
            claims=[],
            ungrounded_claims=[f"claim_{i}" for i in range(10)],
            grounded_claims=[],
        )
        guidance = r.get_revision_guidance()
        # Should only list 5 claims
        listed = [line for line in guidance.split("\n") if line.startswith("- ")]
        assert len(listed) == 5


# ── EnhancedGroundingResult ──────────────────────────────────────────


class TestEnhancedGroundingResult:
    def _make_result(self, **kwargs):
        defaults = {
            "overall_score": 0.5,
            "level": GroundingLevel.PARTIALLY_GROUNDED,
            "claims": [],
            "ungrounded_claims": [],
            "grounded_claims": [],
        }
        defaults.update(kwargs)
        return EnhancedGroundingResult(**defaults)

    def test_has_fabricated_data_true(self):
        r = self._make_result(fabricated_numeric_claims=["fake stat"])
        assert r.has_fabricated_data is True

    def test_has_fabricated_data_false(self):
        r = self._make_result()
        assert r.has_fabricated_data is False

    def test_has_fabricated_data_entity(self):
        r = self._make_result(fabricated_entity_claims=["fake entity"])
        assert r.has_fabricated_data is True

    def test_numeric_verification_rate_all_verified(self):
        claims = [NumericClaim(text="x", value=1.0)] * 2
        r = self._make_result(numeric_claims=claims, verified_numeric_count=2)
        assert r.numeric_verification_rate == 1.0

    def test_numeric_verification_rate_none_verified(self):
        claims = [NumericClaim(text="x", value=1.0)] * 4
        r = self._make_result(numeric_claims=claims, verified_numeric_count=0)
        assert r.numeric_verification_rate == 0.0

    def test_numeric_verification_rate_empty(self):
        r = self._make_result()
        assert r.numeric_verification_rate == 1.0  # No claims = 100% verified

    def test_entity_verification_rate_partial(self):
        claims = [
            EntityClaim(text="x", entity="A", claim_about="y"),
            EntityClaim(text="x", entity="B", claim_about="z"),
        ]
        r = self._make_result(entity_claims=claims, verified_entity_count=1)
        assert r.entity_verification_rate == 0.5

    def test_entity_verification_rate_empty(self):
        r = self._make_result()
        assert r.entity_verification_rate == 1.0

    def test_get_fabrication_warnings(self):
        r = self._make_result(
            fabricated_numeric_claims=["92% on MMLU"],
            fabricated_entity_claims=["OpenAI claim"],
        )
        warnings = r.get_fabrication_warnings()
        assert len(warnings) == 2
        assert any("FABRICATED METRIC" in w for w in warnings)
        assert any("UNVERIFIED ENTITY" in w for w in warnings)


# ── GroundingValidator ───────────────────────────────────────────────


class TestGroundingValidator:
    def test_validate_empty_response(self):
        v = GroundingValidator()
        r = v.validate(source="Some source.", query="q", response="")
        assert r.overall_score == 1.0
        assert r.level == GroundingLevel.FULLY_GROUNDED

    def test_validate_no_claims_detected(self):
        v = GroundingValidator()
        r = v.validate(source="Some source.", query="q", response="Hi OK")
        assert r.overall_score == 1.0
        assert "No factual claims" in r.warnings[0]

    def test_validate_grounded_response(self):
        source = "Python is a programming language created by Guido van Rossum."
        response = "Python is a programming language created by Guido van Rossum."
        v = GroundingValidator()
        r = v.validate(source=source, query="What is Python?", response=response)
        assert r.overall_score > 0.5
        assert len(r.grounded_claims) >= 1

    def test_validate_ungrounded_response(self):
        source = "Python is a programming language."
        response = "Kubernetes deploys microservices automatically with zero downtime capabilities."
        v = GroundingValidator()
        r = v.validate(source=source, query="q", response=response)
        assert r.overall_score < 0.5

    def test_validate_empty_source(self):
        v = GroundingValidator()
        r = v.validate(source="", query="q", response="Python is a programming language.")
        assert r.overall_score == 0.0

    def test_extract_claims_skips_questions(self):
        v = GroundingValidator()
        claims = v._extract_claims("What is Python? It is a language.")
        texts = [c.text for c in claims]
        assert not any(t.endswith("?") for t in texts)

    def test_extract_claims_skips_short_sentences(self):
        v = GroundingValidator(min_claim_words=4)
        claims = v._extract_claims("OK. This is a normal factual sentence about Python.")
        assert len(claims) >= 1
        assert all(len(c.text.split()) >= 4 for c in claims)

    def test_extract_claims_skips_instructions(self):
        v = GroundingValidator()
        claims = v._extract_claims("Please do this. Note: important. Remember: this.")
        assert len(claims) == 0

    def test_extract_claims_hedge_detection(self):
        v = GroundingValidator()
        claims = v._extract_claims("Python might be the best language.")
        assert len(claims) == 1
        assert claims[0].is_factual is False

    def test_extract_claims_citation_detection(self):
        v = GroundingValidator()
        claims = v._extract_claims("Python is popular [1]. It is fast according to benchmarks.")
        assert any(c.is_factual is False for c in claims)

    def test_tokenize_removes_stop_words(self):
        v = GroundingValidator()
        tokens = v._tokenize("the quick brown fox jumps over the lazy dog")
        assert "the" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens

    def test_tokenize_lowercase(self):
        v = GroundingValidator()
        tokens = v._tokenize("PYTHON Programming Language")
        assert "python" in tokens
        assert "programming" in tokens

    def test_tokenize_short_words_filtered(self):
        v = GroundingValidator()
        tokens = v._tokenize("I am a he it")
        assert len(tokens) == 0  # All short or stop words

    def test_determine_level_fully_grounded(self):
        v = GroundingValidator()
        level = v._determine_level(score=0.8, grounded=9, total=10)
        assert level == GroundingLevel.FULLY_GROUNDED

    def test_determine_level_partially_grounded(self):
        v = GroundingValidator()
        level = v._determine_level(score=0.6, grounded=6, total=10)
        assert level == GroundingLevel.PARTIALLY_GROUNDED

    def test_determine_level_weakly_grounded(self):
        v = GroundingValidator()
        level = v._determine_level(score=0.35, grounded=4, total=10)
        assert level == GroundingLevel.WEAKLY_GROUNDED

    def test_determine_level_ungrounded(self):
        v = GroundingValidator()
        level = v._determine_level(score=0.1, grounded=1, total=10)
        assert level == GroundingLevel.UNGROUNDED

    def test_determine_level_zero_total(self):
        v = GroundingValidator()
        level = v._determine_level(score=0.8, grounded=0, total=0)
        assert level == GroundingLevel.FULLY_GROUNDED

    def test_stats_tracking(self):
        v = GroundingValidator()
        v.validate(source="Python is great.", query="q", response="Python is great.")
        stats = v.get_stats()
        assert stats["validations"] == 1

    def test_reset_stats(self):
        v = GroundingValidator()
        v.validate(source="x", query="q", response="")
        v.reset_stats()
        stats = v.get_stats()
        assert stats["validations"] == 0

    def test_custom_threshold(self):
        v = GroundingValidator(grounding_threshold=0.9)
        assert v.grounding_threshold == 0.9

    def test_max_claims_limit(self):
        v = GroundingValidator(max_claims_to_check=2)
        # Many sentences
        response = ". ".join([f"Sentence number {i} about programming" for i in range(10)]) + "."
        v.validate(source="programming", query="q", response=response)
        # Should warn about unchecked claims
        # (just verifying it doesn't crash)


# ── EnhancedGroundingValidator ───────────────────────────────────────


class TestEnhancedGroundingValidator:
    def test_extract_numeric_claims_percentage(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_numeric_claims("Claude scores 92% on MMLU benchmark.")
        assert len(claims) >= 1
        assert any(c.value == 92.0 for c in claims)

    def test_extract_numeric_claims_year(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_numeric_claims("This was released in 2024.")
        assert len(claims) >= 1
        assert any(c.value == 2024.0 for c in claims)

    def test_extract_numeric_claims_empty(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_numeric_claims("No numbers here.")
        assert len(claims) == 0

    def test_extract_entity_claims_company(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_entity_claims("Anthropic released a new model with improved capabilities.")
        assert len(claims) >= 1
        assert any(c.entity == "Anthropic" for c in claims)

    def test_extract_entity_claims_model(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_entity_claims("GPT-4 outperforms all previous models significantly.")
        assert len(claims) >= 1
        assert any("GPT-4" in c.entity for c in claims)

    def test_extract_entity_claims_empty(self):
        v = EnhancedGroundingValidator()
        claims = v.extract_entity_claims("No entities here.")
        assert len(claims) == 0

    def test_classify_entity_company(self):
        v = EnhancedGroundingValidator()
        assert v._classify_entity("OpenAI") == "company"
        assert v._classify_entity("Anthropic") == "company"

    def test_classify_entity_model(self):
        v = EnhancedGroundingValidator()
        assert v._classify_entity("GPT-4") == "model"

    def test_classify_entity_platform(self):
        v = EnhancedGroundingValidator()
        assert v._classify_entity("OpenRouter") == "platform"

    def test_classify_entity_unknown(self):
        v = EnhancedGroundingValidator()
        assert v._classify_entity("FooBar") == "unknown"

    def test_verify_numeric_in_source_exact_match(self):
        v = EnhancedGroundingValidator()
        claim = NumericClaim(text="Score is 92%.", value=92.0, unit="%")
        assert v.verify_numeric_in_source(claim, "The model achieved 92% accuracy.") is True
        assert claim.is_verified is True

    def test_verify_numeric_in_source_with_entity(self):
        v = EnhancedGroundingValidator()
        claim = NumericClaim(text="Claude scores 92%.", value=92.0, entity="Claude")
        source = "In benchmark tests, Claude achieved 92% on MMLU."
        assert v.verify_numeric_in_source(claim, source) is True

    def test_verify_numeric_in_source_entity_mismatch(self):
        v = EnhancedGroundingValidator()
        claim = NumericClaim(text="Claude scores 92%.", value=92.0, entity="Claude")
        source = "GPT-4 achieved 92% on MMLU."
        assert v.verify_numeric_in_source(claim, source) is False

    def test_verify_numeric_in_source_empty(self):
        v = EnhancedGroundingValidator()
        claim = NumericClaim(text="Score is 92%.", value=92.0)
        assert v.verify_numeric_in_source(claim, "") is False

    def test_verify_numeric_tolerance(self):
        v = EnhancedGroundingValidator(numeric_tolerance=0.02)
        claim = NumericClaim(text="Score is 92%.", value=92.0)
        # 91.5 is within 2% tolerance of 92.0 (diff=0.5, tolerance=1.84)
        assert v.verify_numeric_in_source(claim, "The score was 91.5% in the test.") is True

    def test_extract_metric_from_context_benchmark(self):
        v = EnhancedGroundingValidator()
        metric = v._extract_metric_from_context("Claude scores 92% on MMLU benchmark.")
        assert metric == "MMLU"

    def test_extract_metric_from_context_none(self):
        v = EnhancedGroundingValidator()
        metric = v._extract_metric_from_context("The price is 100 dollars.")
        assert metric is None

    def test_extract_entity_from_context(self):
        v = EnhancedGroundingValidator()
        entity = v._extract_entity_from_context("OpenAI released GPT-4 last year.")
        assert entity is not None

    def test_extract_claim_about_entity_meaningful(self):
        v = EnhancedGroundingValidator()
        claim = v._extract_claim_about_entity("OpenAI released a new model.", "OpenAI")
        assert claim is not None
        assert "released" in claim

    def test_extract_claim_about_entity_too_short(self):
        v = EnhancedGroundingValidator()
        claim = v._extract_claim_about_entity("OpenAI is.", "OpenAI")
        assert claim is None
