"""Citation validation and enforcement service.

Phase 6 Enhancement: Adds semantic verification that citations actually
support claims, not just format checking.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.citation_discipline import (
    CitationConfig,
    CitationValidationResult,
    CitedClaim,
    ClaimType,
)
from app.domain.models.source_quality import SourceQualityScore
from app.domain.services.agents.grounding_validator import EnhancedGroundingValidator
from app.domain.services.agents.url_verification import URLVerificationService

logger = logging.getLogger(__name__)


# =============================================================================
# Phase 6: Semantic Citation Verification Models
# =============================================================================


@dataclass
class CitationSemanticResult:
    """Result of semantic verification between a claim and its citation.

    Phase 6 Enhancement: Goes beyond format checking to verify citations
    actually support the claims they're attached to.
    """

    claim_text: str
    citation_id: str
    source_url: str | None = None

    # Semantic matching results
    is_semantically_matched: bool = False
    semantic_score: float = 0.0  # 0.0-1.0

    # Numeric verification
    has_numeric_claim: bool = False
    numeric_verified: bool = False
    claimed_number: float | None = None
    source_number: float | None = None

    # Entity verification
    has_entity_claim: bool = False
    entity_verified: bool = False
    claimed_entity: str | None = None

    # Evidence
    supporting_excerpt: str | None = None
    verification_method: str = "keyword"  # keyword, semantic, numeric, llm

    # Issues
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if citation validly supports the claim."""
        if self.has_numeric_claim and not self.numeric_verified:
            return False
        if self.has_entity_claim and not self.entity_verified:
            return False
        return self.is_semantically_matched or self.semantic_score >= 0.5

    @property
    def confidence(self) -> float:
        """Overall confidence that citation supports claim."""
        scores = [self.semantic_score]
        if self.has_numeric_claim:
            scores.append(1.0 if self.numeric_verified else 0.0)
        if self.has_entity_claim:
            scores.append(1.0 if self.entity_verified else 0.0)
        return sum(scores) / len(scores) if scores else 0.0


@dataclass
class EnhancedCitationValidationResult:
    """Extended validation result with semantic verification.

    Phase 6 Enhancement: Includes semantic matching results for all claims.
    """

    base_result: CitationValidationResult
    semantic_results: list[CitationSemanticResult] = field(default_factory=list)

    # Summary metrics
    semantically_verified_count: int = 0
    semantically_failed_count: int = 0
    numeric_verified_count: int = 0
    numeric_failed_count: int = 0

    @property
    def has_semantic_issues(self) -> bool:
        """Check if any citations failed semantic verification."""
        return self.semantically_failed_count > 0 or self.numeric_failed_count > 0

    def get_failed_citations(self) -> list[CitationSemanticResult]:
        """Get citations that failed semantic verification."""
        return [r for r in self.semantic_results if not r.is_valid]

    def get_semantic_summary(self) -> str:
        """Get a summary of semantic verification results."""
        return (
            f"Semantic: {self.semantically_verified_count}/{len(self.semantic_results)} verified, "
            f"Numeric: {self.numeric_verified_count} verified, {self.numeric_failed_count} failed"
        )


CLAIM_EXTRACTION_PROMPT = """Analyze the following content and extract all claims that require citations.

For each claim, identify:
1. claim_text: The exact claim being made
2. claim_type: One of [factual, statistical, quotation, inference, opinion, common]
3. needs_citation: Whether this claim requires a source citation
4. existing_citation: Any citation ID already present (e.g., [1], [source-a])

Content to analyze:
---
{content}
---

Available citations:
{citations}

Respond with JSON:
{{
  "claims": [
    {{
      "claim_text": "...",
      "claim_type": "...",
      "needs_citation": true/false,
      "existing_citation": "..." or null,
      "confidence": 0.0-1.0
    }}
  ]
}}"""


class CitationValidator:
    """Validates and enforces citation discipline in content."""

    def __init__(self, llm: LLM, config: CitationConfig | None = None):
        self.llm = llm
        self.config = config or CitationConfig()

    async def validate(
        self,
        content: str,
        available_citations: dict[str, dict[str, Any]],
        source_scores: dict[str, SourceQualityScore] | None = None,
    ) -> CitationValidationResult:
        """Validate citation discipline in content.

        Args:
            content: The content to validate
            available_citations: Dict of citation_id -> {url, title, excerpt}
            source_scores: Optional quality scores for sources

        Returns:
            CitationValidationResult with detailed analysis
        """
        # Extract claims using LLM
        claims = await self._extract_claims(content, available_citations)

        # Validate each claim
        validated_claims: list[CitedClaim] = []
        missing_citations: list[str] = []
        weak_citations: list[str] = []

        for claim_data in claims:
            claim = self._validate_claim(claim_data, available_citations, source_scores)
            validated_claims.append(claim)

            # Track issues
            if self.config.requires_citation(claim.claim_type):
                if not claim.citation_ids:
                    missing_citations.append(claim.claim_text[:100])
                elif source_scores:
                    # Check citation quality
                    for cid in claim.citation_ids:
                        if cid in available_citations:
                            url = available_citations[cid].get("url", "")
                            if (
                                url in source_scores
                                and source_scores[url].reliability_score < self.config.min_source_reliability
                            ):
                                weak_citations.append(f"{claim.claim_text[:50]}... (source: {url})")

        # Calculate scores
        total = len(validated_claims)
        cited = sum(1 for c in validated_claims if c.citation_ids)
        uncited_factual = sum(
            1 for c in validated_claims if self.config.requires_citation(c.claim_type) and not c.citation_ids
        )

        coverage = cited / total if total > 0 else 0.0

        # Quality based on source reliability
        quality_scores: list[float] = []
        for claim in validated_claims:
            if claim.citation_ids and source_scores:
                for cid in claim.citation_ids:
                    if cid in available_citations:
                        url = available_citations[cid].get("url", "")
                        if url in source_scores:
                            quality_scores.append(source_scores[url].reliability_score)

        quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5

        # Determine validity
        is_valid = coverage >= self.config.min_coverage_score and quality >= self.config.min_quality_score

        if self.config.fail_on_uncited_factual and uncited_factual > 0:
            is_valid = False

        return CitationValidationResult(
            is_valid=is_valid,
            total_claims=total,
            cited_claims=cited,
            uncited_factual_claims=uncited_factual,
            claims=validated_claims,
            missing_citations=missing_citations,
            weak_citations=weak_citations,
            citation_coverage=coverage,
            citation_quality=quality,
        )

    async def _extract_claims(
        self,
        content: str,
        citations: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract claims from content using LLM."""
        # Format citations for prompt
        citation_str = "\n".join(
            f"[{cid}]: {c.get('title', 'Unknown')} - {c.get('url', 'No URL')}" for cid, c in citations.items()
        )

        prompt = CLAIM_EXTRACTION_PROMPT.format(
            content=content[:6000],
            citations=citation_str or "No citations available",
        )

        try:
            response = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            response_content = response.get("content", "")
            data = json.loads(response_content)
            return data.get("claims", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse claim extraction response")
            # Fallback to basic extraction
            return self._extract_claims_basic(content)
        except Exception as e:
            logger.warning(f"LLM claim extraction failed: {e}")
            return self._extract_claims_basic(content)

    def _extract_claims_basic(self, content: str) -> list[dict[str, Any]]:
        """Basic claim extraction using heuristics."""
        claims: list[dict[str, Any]] = []

        # Split into sentences
        sentences = re.split(r"[.!?]+", content)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue

            # Determine claim type based on patterns
            claim_type = ClaimType.FACTUAL.value

            if re.search(r"\d+%|\d+\.\d+|million|billion|thousand", sentence, re.IGNORECASE):
                claim_type = ClaimType.STATISTICAL.value
            elif re.search(r'["\'](.{10,}?)["\']', sentence):
                claim_type = ClaimType.QUOTATION.value
            elif re.search(r"\bI think\b|\bbelieve\b|\bopinion\b|\bfeel\b", sentence, re.IGNORECASE):
                claim_type = ClaimType.OPINION.value
            elif re.search(r"\btherefore\b|\bthus\b|\bimplies\b|\bsuggests\b|\bindicates\b", sentence, re.IGNORECASE):
                claim_type = ClaimType.INFERENCE.value
            elif re.search(r"\bgenerally\b|\bcommonly\b|\bwell.known\b|\bobviously\b", sentence, re.IGNORECASE):
                claim_type = ClaimType.COMMON_KNOWLEDGE.value

            # Check for existing citations
            citation_match = re.search(r"\[(\d+|[\w-]+)\]", sentence)

            claims.append(
                {
                    "claim_text": sentence,
                    "claim_type": claim_type,
                    "needs_citation": claim_type in ["factual", "statistical", "quotation"],
                    "existing_citation": citation_match.group(1) if citation_match else None,
                    "confidence": 0.5,
                }
            )

        return claims

    def _validate_claim(
        self,
        claim_data: dict[str, Any],
        citations: dict[str, dict[str, Any]],
        source_scores: dict[str, SourceQualityScore] | None,
    ) -> CitedClaim:
        """Validate a single claim."""
        try:
            claim_type = ClaimType(claim_data.get("claim_type", "factual"))
        except ValueError:
            claim_type = ClaimType.FACTUAL

        # Find citation IDs
        citation_ids: list[str] = []
        if claim_data.get("existing_citation"):
            citation_ids.append(str(claim_data["existing_citation"]))

        # Also extract any inline citations
        claim_text = claim_data.get("claim_text", "")
        inline_citations = re.findall(r"\[(\d+|[\w-]+)\]", claim_text)
        citation_ids.extend(inline_citations)
        citation_ids = list(set(citation_ids))  # Dedupe

        # Get supporting excerpts
        excerpts: list[str] = []
        for cid in citation_ids:
            if cid in citations and citations[cid].get("excerpt"):
                excerpts.append(str(citations[cid]["excerpt"]))

        # Determine verification status
        is_verified = bool(citation_ids) and claim_type != ClaimType.INFERENCE

        # Calculate confidence based on source quality
        confidence = float(claim_data.get("confidence", 0.5))
        if citation_ids and source_scores:
            reliability_scores = []
            for cid in citation_ids:
                if cid in citations:
                    url = citations[cid].get("url", "")
                    if url in source_scores:
                        reliability_scores.append(source_scores[url].reliability_score)
            if reliability_scores:
                confidence = sum(reliability_scores) / len(reliability_scores)

        return CitedClaim(
            claim_text=claim_text,
            claim_type=claim_type,
            citation_ids=citation_ids,
            supporting_excerpts=excerpts,
            is_verified=is_verified,
            confidence=confidence,
        )

    def enforce_citations(
        self,
        content: str,
        validation_result: CitationValidationResult,
    ) -> str:
        """Add caveats to content for uncited claims.

        Args:
            content: Original content
            validation_result: Validation result with claims

        Returns:
            Content with caveats added for uncited claims
        """
        if not self.config.auto_add_caveats:
            return content

        modified = content

        for claim in validation_result.claims:
            if claim.requires_caveat and claim.caveat_text and claim.claim_text in modified:
                # Insert caveat after the claim
                modified = modified.replace(
                    claim.claim_text,
                    f"{claim.claim_text} {claim.caveat_text}",
                    1,  # Only replace first occurrence
                )

        return modified

    def get_citation_suggestions(
        self,
        validation_result: CitationValidationResult,
        available_citations: dict[str, dict[str, Any]],
    ) -> dict[str, list[str]]:
        """Suggest citations for uncited claims.

        Args:
            validation_result: Validation result with claims
            available_citations: Available citations to suggest

        Returns:
            Dict mapping claim text to suggested citation IDs
        """
        suggestions: dict[str, list[str]] = {}

        for claim in validation_result.get_uncited_claims():
            if not self.config.requires_citation(claim.claim_type):
                continue

            claim_lower = claim.claim_text.lower()
            suggested: list[str] = []

            for cid, citation in available_citations.items():
                # Check if citation content is relevant to claim
                title = citation.get("title", "").lower()
                excerpt = citation.get("excerpt", "").lower()

                # Simple keyword matching
                claim_words = set(re.findall(r"\w+", claim_lower))
                title_words = set(re.findall(r"\w+", title))
                excerpt_words = set(re.findall(r"\w+", excerpt))

                overlap = claim_words & (title_words | excerpt_words)
                if len(overlap) >= 2:  # At least 2 words in common
                    suggested.append(cid)

            if suggested:
                suggestions[claim.claim_text[:100]] = suggested[:3]  # Top 3 suggestions

        return suggestions

    # =========================================================================
    # Phase 6: Semantic Citation Verification
    # =========================================================================

    async def validate_with_semantic_verification(
        self,
        content: str,
        available_citations: dict[str, dict[str, Any]],
        source_contents: dict[str, str] | None = None,
        source_scores: dict[str, SourceQualityScore] | None = None,
    ) -> EnhancedCitationValidationResult:
        """Validate citations with semantic verification.

        Phase 6 Enhancement: Goes beyond format checking to verify that
        citations semantically support the claims they're attached to.

        Args:
            content: The content to validate
            available_citations: Dict of citation_id -> {url, title, excerpt}
            source_contents: Dict of citation_id -> full source content
            source_scores: Optional quality scores for sources

        Returns:
            EnhancedCitationValidationResult with semantic verification
        """
        # First run base validation
        base_result = await self.validate(content, available_citations, source_scores)

        # Initialize enhanced validator for numeric checking
        grounding_validator = EnhancedGroundingValidator()

        # Semantic verification for each cited claim
        semantic_results: list[CitationSemanticResult] = []
        semantically_verified = 0
        semantically_failed = 0
        numeric_verified = 0
        numeric_failed = 0

        for claim in base_result.claims:
            if not claim.citation_ids:
                continue

            for cid in claim.citation_ids:
                if cid not in available_citations:
                    continue

                citation = available_citations[cid]
                source_url = citation.get("url")

                # Get source content (use excerpt if full content not available)
                source_content = ""
                if source_contents and cid in source_contents:
                    source_content = source_contents[cid]
                elif citation.get("excerpt"):
                    source_content = citation["excerpt"]

                # Run semantic verification
                result = self._verify_citation_semantic_match(
                    claim_text=claim.claim_text,
                    citation_id=cid,
                    source_url=source_url,
                    source_content=source_content,
                    grounding_validator=grounding_validator,
                )

                semantic_results.append(result)

                # Update counts
                if result.is_semantically_matched:
                    semantically_verified += 1
                else:
                    semantically_failed += 1

                if result.has_numeric_claim:
                    if result.numeric_verified:
                        numeric_verified += 1
                    else:
                        numeric_failed += 1

        return EnhancedCitationValidationResult(
            base_result=base_result,
            semantic_results=semantic_results,
            semantically_verified_count=semantically_verified,
            semantically_failed_count=semantically_failed,
            numeric_verified_count=numeric_verified,
            numeric_failed_count=numeric_failed,
        )

    def _verify_citation_semantic_match(
        self,
        claim_text: str,
        citation_id: str,
        source_url: str | None,
        source_content: str,
        grounding_validator: EnhancedGroundingValidator,
    ) -> CitationSemanticResult:
        """Verify that a citation semantically supports its claim.

        Args:
            claim_text: The claim text
            citation_id: Citation ID
            source_url: Source URL
            source_content: Source content to check against
            grounding_validator: Validator for numeric/entity checking

        Returns:
            CitationSemanticResult with verification details
        """
        result = CitationSemanticResult(
            claim_text=claim_text,
            citation_id=citation_id,
            source_url=source_url,
        )

        if not source_content:
            result.issues.append("No source content available for verification")
            return result

        # Extract numeric claims from the claim text
        numeric_claims = grounding_validator.extract_numeric_claims(claim_text)
        if numeric_claims:
            result.has_numeric_claim = True
            result.claimed_number = numeric_claims[0].value

            # Verify numeric claim against source
            for nc in numeric_claims:
                if grounding_validator.verify_numeric_in_source(nc, source_content):
                    result.numeric_verified = True
                    result.source_number = nc.value
                    result.supporting_excerpt = nc.verification_source
                    break

            if not result.numeric_verified:
                result.issues.append(f"Numeric claim ({result.claimed_number}) not found in source")

        # Extract entity claims
        entity_claims = grounding_validator.extract_entity_claims(claim_text)
        if entity_claims:
            result.has_entity_claim = True
            result.claimed_entity = entity_claims[0].entity

            # Verify entity claim against source
            for ec in entity_claims:
                if grounding_validator.verify_entity_in_source(ec, source_content):
                    result.entity_verified = True
                    break

            if not result.entity_verified:
                result.issues.append(f"Entity claim ({result.claimed_entity}) not verified in source")

        # Calculate semantic similarity using word overlap (Jaccard)
        semantic_score = self._calculate_semantic_score(claim_text, source_content)
        result.semantic_score = semantic_score
        result.is_semantically_matched = semantic_score >= 0.3

        if not result.is_semantically_matched:
            result.issues.append(f"Low semantic similarity ({semantic_score:.2f}) between claim and source")

        # Set verification method
        if result.numeric_verified:
            result.verification_method = "numeric"
        elif result.entity_verified:
            result.verification_method = "entity"
        elif result.is_semantically_matched:
            result.verification_method = "semantic"
        else:
            result.verification_method = "failed"

        return result

    def _calculate_semantic_score(
        self,
        claim_text: str,
        source_content: str,
    ) -> float:
        """Calculate semantic similarity between claim and source.

        Uses Jaccard similarity of meaningful words.

        Args:
            claim_text: The claim text
            source_content: Source content

        Returns:
            Similarity score 0.0-1.0
        """
        # Tokenize and normalize
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "and",
            "but",
            "or",
            "nor",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
        }

        def tokenize(text: str) -> set[str]:
            words = re.findall(r"\b[a-z]+\b", text.lower())
            return {w for w in words if w not in stop_words and len(w) > 2}

        claim_words = tokenize(claim_text)
        source_words = tokenize(source_content)

        if not claim_words or not source_words:
            return 0.0

        # Jaccard similarity
        intersection = len(claim_words & source_words)
        union = len(claim_words | source_words)

        return intersection / union if union > 0 else 0.0

    async def verify_urls_in_citations(
        self,
        available_citations: dict[str, dict[str, Any]],
        session_urls: set[str] | None = None,
    ) -> dict[str, bool]:
        """Verify that citation URLs exist and were visited.

        Phase 6 Enhancement: Uses URL verification service to check citations.

        Args:
            available_citations: Dict of citation_id -> {url, title, excerpt}
            session_urls: Set of URLs visited during the session

        Returns:
            Dict of citation_id -> is_valid
        """
        url_service = URLVerificationService()
        results: dict[str, bool] = {}

        for cid, citation in available_citations.items():
            url = citation.get("url")
            if not url:
                results[cid] = False
                continue

            # Check if URL is a placeholder
            if url_service.detect_placeholder_url(url):
                logger.warning(f"Citation {cid} has placeholder URL: {url}")
                results[cid] = False
                continue

            # Check if URL was visited (if session URLs provided)
            if session_urls:
                was_visited = url_service.verify_url_was_visited(url, session_urls)
                if not was_visited:
                    logger.warning(f"Citation {cid} URL was not visited: {url}")
                    results[cid] = False
                    continue

            results[cid] = True

        return results
