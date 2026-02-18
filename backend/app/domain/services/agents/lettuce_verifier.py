"""LettuceDetect-based hallucination verification.

Replaces Chain-of-Verification (CoVe) with a ModernBERT encoder-based approach
that performs token-level hallucination detection. Zero LLM calls required.

Key advantages over CoVe:
- ~100ms latency vs ~30s (300x faster)
- No LLM API cost per verification
- Grounded in provided context (not parametric memory)
- Token-level precision: pinpoints exact hallucinated spans

Architecture:
    LettuceVerifier wraps HallucinationDetector from the `lettucedetect` package.
    Model is loaded lazily via get_lettuce_verifier() singleton to avoid repeated
    initialization (~100-300MB model weight in memory).

Usage:
    verifier = get_lettuce_verifier()
    result = verifier.verify(
        context=["France has 67 million people...", "Paris is the capital."],
        question="What is the population of France?",
        answer="The population of France is 69 million.",
    )
    if result.has_hallucinations:
        # result.hallucinated_spans contains exact positions
        ...
"""

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Lazy import — lettucedetect may not be installed in all environments
_HallucinationDetector = None


def _get_detector_class():
    """Lazy import of HallucinationDetector to avoid import-time failures."""
    global _HallucinationDetector
    if _HallucinationDetector is None:
        from lettucedetect.models.inference import HallucinationDetector

        _HallucinationDetector = HallucinationDetector
    return _HallucinationDetector


@dataclass
class HallucinatedSpan:
    """A detected hallucinated span in the answer text."""

    start: int
    end: int
    text: str
    confidence: float


@dataclass
class LettuceVerificationResult:
    """Result of LettuceDetect hallucination verification."""

    original_response: str
    hallucinated_spans: list[HallucinatedSpan] = field(default_factory=list)
    confidence_score: float = 1.0  # 1.0 = fully supported, 0.0 = fully hallucinated
    processing_time_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""

    @property
    def has_hallucinations(self) -> bool:
        """Check if any hallucinated spans were detected."""
        return len(self.hallucinated_spans) > 0

    @property
    def hallucination_ratio(self) -> float:
        """Ratio of hallucinated text to total answer length."""
        if not self.original_response or not self.hallucinated_spans:
            return 0.0
        hallucinated_chars = sum(s.end - s.start for s in self.hallucinated_spans)
        return hallucinated_chars / len(self.original_response)

    def get_summary(self) -> str:
        """Get a human-readable summary of the verification."""
        if self.skipped:
            return f"Verification skipped: {self.skip_reason}"
        if not self.hallucinated_spans:
            return f"All claims supported (confidence: {self.confidence_score:.2f}, {self.processing_time_ms:.0f}ms)"
        return (
            f"Found {len(self.hallucinated_spans)} hallucinated span(s), "
            f"confidence: {self.confidence_score:.2f}, "
            f"hallucination ratio: {self.hallucination_ratio:.1%}, "
            f"{self.processing_time_ms:.0f}ms"
        )


class LettuceVerifier:
    """Encoder-based hallucination detector using LettuceDetect.

    Uses a ModernBERT model (17-149M params) to perform token-level
    classification on (context, question, answer) triplets. Each token
    in the answer is classified as supported or hallucinated.

    Attributes:
        model_path: HuggingFace model path for the encoder
        confidence_threshold: Minimum confidence to flag a span as hallucinated
        min_response_length: Minimum answer length to trigger verification
    """

    def __init__(
        self,
        model_path: str = "KRLabsOrg/tinylettuce-ettin-17m-en",
        confidence_threshold: float = 0.5,
        min_response_length: int = 200,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.min_response_length = min_response_length
        self._detector = None
        self._load_error: str | None = None

    def _ensure_loaded(self) -> bool:
        """Lazily load the model on first use. Returns True if ready."""
        if self._detector is not None:
            return True
        if self._load_error is not None:
            return False  # Already failed once, don't retry

        try:
            # Authenticate with HuggingFace Hub if token is available to avoid
            # unauthenticated rate limits during model download.
            hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
            if hf_token:
                try:
                    from huggingface_hub import login as hf_login

                    hf_login(token=hf_token, add_to_git_credential=False)
                    logger.debug("Authenticated with HuggingFace Hub")
                except Exception as auth_err:
                    logger.debug("HF Hub auth skipped: %s", auth_err)

            detector_cls = _get_detector_class()
            logger.info("Loading LettuceDetect model: %s", self.model_path)
            start = time.monotonic()
            self._detector = detector_cls(
                method="transformer",
                model_path=self.model_path,
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info("LettuceDetect model loaded in %.0fms", elapsed_ms)
            return True
        except Exception as e:
            self._load_error = str(e)
            logger.error("Failed to load LettuceDetect model: %s", e)
            return False

    def verify(
        self,
        context: list[str],
        question: str,
        answer: str,
    ) -> LettuceVerificationResult:
        """Verify an answer against provided context for hallucinations.

        Args:
            context: List of source text chunks the answer should be grounded on.
                     Each chunk is a separate search result or page excerpt.
                     LettuceDetect's predict() API expects list[str].
            question: The original user question/query.
            answer: The generated answer to verify.

        Returns:
            LettuceVerificationResult with hallucinated spans and metrics.
        """
        start_time = time.monotonic()

        # Skip short responses
        if len(answer) < self.min_response_length:
            return LettuceVerificationResult(
                original_response=answer,
                confidence_score=0.7,
                skipped=True,
                skip_reason=f"Response too short ({len(answer)} chars < {self.min_response_length})",
                processing_time_ms=(time.monotonic() - start_time) * 1000,
            )

        # Skip if no context to ground against
        total_context_len = sum(len(c.strip()) for c in context)
        if not context or total_context_len < 50:
            return LettuceVerificationResult(
                original_response=answer,
                confidence_score=0.7,
                skipped=True,
                skip_reason="Insufficient context for grounding",
                processing_time_ms=(time.monotonic() - start_time) * 1000,
            )

        # Ensure model is loaded
        if not self._ensure_loaded():
            return LettuceVerificationResult(
                original_response=answer,
                confidence_score=0.5,
                skipped=True,
                skip_reason=f"Model load failed: {self._load_error}",
                processing_time_ms=(time.monotonic() - start_time) * 1000,
            )

        try:
            # Truncate each context chunk to keep total under 4K chars
            # for ModernBERT's context window
            truncated_chunks: list[str] = []
            total_len = 0
            for chunk in context:
                if total_len + len(chunk) > 4000:
                    remaining = 4000 - total_len
                    if remaining > 50:
                        truncated_chunks.append(chunk[:remaining])
                    break
                truncated_chunks.append(chunk)
                total_len += len(chunk)

            predictions = self._detector.predict(
                context=truncated_chunks,
                question=question,
                answer=answer,
                output_format="spans",
            )

            # Parse span predictions
            hallucinated_spans = []
            for span in predictions:
                confidence = span.get("confidence", 0.0)
                if confidence >= self.confidence_threshold:
                    hallucinated_spans.append(
                        HallucinatedSpan(
                            start=span["start"],
                            end=span["end"],
                            text=span.get("text", answer[span["start"] : span["end"]]),
                            confidence=confidence,
                        )
                    )

            # Calculate overall confidence (1.0 = fully supported)
            if hallucinated_spans:
                avg_hallucination_confidence = sum(s.confidence for s in hallucinated_spans) / len(hallucinated_spans)
                # Weighted by how much text is hallucinated
                result = LettuceVerificationResult(
                    original_response=answer,
                    hallucinated_spans=hallucinated_spans,
                    confidence_score=1.0
                    - avg_hallucination_confidence * self._hallucination_weight(hallucinated_spans, answer),
                    processing_time_ms=(time.monotonic() - start_time) * 1000,
                )
            else:
                result = LettuceVerificationResult(
                    original_response=answer,
                    confidence_score=1.0,
                    processing_time_ms=(time.monotonic() - start_time) * 1000,
                )

            logger.info("LettuceDetect: %s", result.get_summary())
            return result

        except Exception as e:
            logger.warning("LettuceDetect verification failed: %s", e)
            return LettuceVerificationResult(
                original_response=answer,
                confidence_score=0.5,
                skipped=True,
                skip_reason=f"Verification error: {e}",
                processing_time_ms=(time.monotonic() - start_time) * 1000,
            )

    @staticmethod
    def _hallucination_weight(spans: list[HallucinatedSpan], answer: str) -> float:
        """Calculate weight of hallucinated content relative to full answer."""
        if not answer:
            return 0.0
        hallucinated_chars = sum(s.end - s.start for s in spans)
        ratio = hallucinated_chars / len(answer)
        # Clamp to [0.1, 1.0] — even small hallucinations lower confidence
        return max(0.1, min(1.0, ratio))

    def redact_hallucinations(self, answer: str, spans: list[HallucinatedSpan]) -> str:
        """Remove or mark hallucinated spans in the answer.

        Removes hallucinated spans with a neutral omission marker. Spans are
        processed in reverse order to preserve character positions.

        Args:
            answer: Original answer text.
            spans: Hallucinated spans detected by verify().

        Returns:
            Answer with hallucinated spans marked.
        """
        if not spans:
            return answer

        # Sort spans by start position in reverse order to maintain positions
        sorted_spans = sorted(spans, key=lambda s: s.start, reverse=True)
        result = answer
        for span in sorted_spans:
            result = result[: span.start] + " […] " + result[span.end :]
        return result


# ── Singleton ──────────────────────────────────────────────────────────

_verifier_instance: LettuceVerifier | None = None


def get_lettuce_verifier() -> LettuceVerifier:
    """Get or create the singleton LettuceVerifier instance.

    Reads model path and thresholds from Settings on first call.

    Returns:
        LettuceVerifier singleton instance.
    """
    global _verifier_instance
    if _verifier_instance is None:
        try:
            from app.core.config import get_settings

            settings = get_settings()
            _verifier_instance = LettuceVerifier(
                model_path=settings.lettuce_model_path,
                confidence_threshold=settings.lettuce_confidence_threshold,
                min_response_length=settings.lettuce_min_response_length,
            )
        except Exception:
            # Fallback to defaults if settings unavailable
            _verifier_instance = LettuceVerifier()
    return _verifier_instance
