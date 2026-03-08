"""Fast AI-powered refinement for first acknowledgment messages."""

from __future__ import annotations

import asyncio
import logging
import re
import time

from app.domain.exceptions.base import LLMKeysExhaustedError
from app.domain.external.llm import LLM
from app.domain.external.observability import get_metrics
from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator

logger = logging.getLogger(__name__)


class FastAcknowledgmentRefiner:
    """Generate a polished first reply quickly, with deterministic fallback."""

    def __init__(
        self,
        llm: LLM,
        fallback_generator: AcknowledgmentGenerator,
        timeout_seconds: float = 2.5,  # Increased from 0.25s to allow LLM response completion
        traceback_sample_rate: float = 0.05,
    ) -> None:
        self._llm = llm
        self._fallback = fallback_generator
        self._timeout_seconds = timeout_seconds
        self._traceback_sample_rate = max(0.0, min(1.0, traceback_sample_rate))
        self._error_count = 0

    async def generate(self, user_message: str) -> str:
        start_time = time.perf_counter()
        metrics = get_metrics()
        fallback = self._fallback.generate(user_message)

        try:
            refined = await asyncio.wait_for(self._generate_with_llm(user_message), timeout=self._timeout_seconds)
            refined = self._sanitize(refined)
            if not refined:
                elapsed = time.perf_counter() - start_time
                metrics.record_counter("fast_ack_refiner_total", labels={"status": "fallback", "reason": "empty"})
                metrics.record_histogram("fast_ack_refiner_latency_seconds", elapsed, labels={"status": "fallback"})
                logger.info("Fast ack refiner fallback: empty response")
                return fallback

            if self._should_prefer_fallback(refined, fallback):
                elapsed = time.perf_counter() - start_time
                metrics.record_counter("fast_ack_refiner_total", labels={"status": "fallback", "reason": "low_quality"})
                metrics.record_histogram("fast_ack_refiner_latency_seconds", elapsed, labels={"status": "fallback"})
                logger.info("Fast ack refiner fallback: low_quality")
                return fallback

            elapsed = time.perf_counter() - start_time
            metrics.record_counter("fast_ack_refiner_total", labels={"status": "success", "reason": "refined"})
            metrics.record_histogram("fast_ack_refiner_latency_seconds", elapsed, labels={"status": "success"})
            return refined
        except TimeoutError:
            elapsed = time.perf_counter() - start_time
            metrics.record_counter("fast_ack_refiner_total", labels={"status": "fallback", "reason": "timeout"})
            metrics.record_histogram("fast_ack_refiner_latency_seconds", elapsed, labels={"status": "fallback"})
            logger.debug("Fast ack refiner fallback: timeout")
            return fallback
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            metrics.record_counter("fast_ack_refiner_total", labels={"status": "fallback", "reason": "error"})
            metrics.record_histogram("fast_ack_refiner_latency_seconds", elapsed, labels={"status": "fallback"})
            reason_code = type(exc).__name__

            # API key exhaustion: expected degradation — log at debug to avoid spam
            if isinstance(exc, LLMKeysExhaustedError):
                logger.debug("Fast ack refiner fallback: keys exhausted (%s)", exc)
            else:
                self._error_count += 1
                if self._should_sample_traceback():
                    logger.warning(
                        "Fast ack refiner fallback: reason=error reason_code=%s sampled_traceback=true",
                        reason_code,
                        exc_info=True,
                    )
                else:
                    logger.warning(
                        "Fast ack refiner fallback: reason=error reason_code=%s sampled_traceback=false",
                        reason_code,
                    )
            return fallback

    async def _generate_with_llm(self, user_message: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You write the first quick acknowledgment before planning begins.\n"
                    "Rules:\n"
                    "- Return exactly 1-2 sentences, plain text.\n"
                    "- Start with: Got it!\n"
                    "- Be professional, direct, and action-oriented.\n"
                    "- Correct obvious typos and awkward phrasing from the user request.\n"
                    "- State what you will do next immediately (review/research/build/create/fix as appropriate).\n"
                    "- You may include a brief time estimate (e.g. 'This should take about 5-10 minutes.').\n"
                    "- Do not ask follow-up questions.\n"
                    "- Do not include bullet points or markdown.\n"
                    "- NEVER mention specific search sites, sources, or platforms (Reddit, Google, Stack Overflow,\n"
                    "  GitHub, Wikipedia, forums, blogs, etc.). Just say 'research' or 'look into'.\n"
                    "- NEVER expand vague references into specific version numbers, model names, or product details.\n"
                    "  If the user says 'latest Claude' just say 'latest Claude' — do NOT guess 'Claude 3.5 Sonnet'.\n"
                    "  Mirror the user's own wording for product/model names."
                ),
            },
            {"role": "user", "content": user_message},
        ]
        response = await self._llm.ask(messages=messages, enable_caching=False)
        return str(response.get("content", "")).strip()

    def _sanitize(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        if not normalized:
            return ""

        # Remove common noisy phrasing artifacts from user list-style prompts.
        normalized = re.sub(
            r"\bon\s+report\s+that\s+covers\s+the\s+following\s+(topics?|items?|sections?)\b",
            r"on the following \1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\b(following\s+(?:topics?|items?|sections?))\s*:\s*(?:\d+|[ivxlcdm]+|[a-zA-Z])(?:[.)])?\s*$",
            r"\1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\bon\s+following\s+(topics?|items?|sections?)\b",
            r"on the following \1",
            normalized,
            flags=re.IGNORECASE,
        )

        # Strip specific source/site mentions the LLM may hallucinate.
        _sites = (
            r"Reddit|Google|Stack\s*Overflow|GitHub|Wikipedia|Hacker\s*News|"
            r"Quora|Medium|Twitter|X\.com|YouTube|forums?|blogs?"
        )
        # Pattern 1: "including searching Reddit and other sources"
        normalized = re.sub(
            rf",?\s*(?:including\s+)?(?:by\s+)?(?:searching|checking|browsing|looking\s+at|from)\s+"
            rf"(?:{_sites})(?:\s*,?\s*(?:and\s+)?(?:{_sites}))*"
            rf"(?:\s+and\s+other\s+sources?)?(?:\s+for\s+[\w\s]{{1,40}})?",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        # Pattern 2: "on Reddit", "via Reddit", "through Reddit", "using Reddit"
        normalized = re.sub(
            rf"\s+(?:on|via|through|using|across)\s+(?:{_sites})(?:\s*,?\s*(?:and\s+)?(?:{_sites}))*"
            rf"(?:\s+and\s+other\s+(?:sources?|platforms?|sites?|communities?))?",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        # Pattern 3: standalone "Reddit research", "Reddit discussions", etc.
        normalized = re.sub(
            rf"\b(?:{_sites})\s+(?:research|discussions?|threads?|posts?|results?|sources?|data)\b",
            "online research",
            normalized,
            flags=re.IGNORECASE,
        )
        # Pattern 4: bare site names remaining (last resort — catches "including Reddit")
        normalized = re.sub(
            rf",?\s*(?:including\s+)?(?:{_sites})(?:\s*,?\s*(?:and\s+)?(?:{_sites}))*"
            rf"(?:\s+and\s+other\s+(?:sources?|platforms?|sites?|communities?))?",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        # Collapse any resulting double spaces or orphaned punctuation
        normalized = re.sub(r"\s*\.\s*\.", ".", normalized)
        normalized = re.sub(r"  +", " ", normalized).strip()

        # Enforce required opener and concise length boundary.
        if not normalized.startswith("Got it!"):
            normalized = f"Got it! {normalized}"
        if len(normalized) > 300:
            normalized = normalized[:300].rstrip(" ,;:")
            if not normalized.endswith((".", "!", "?")):
                normalized += "."
        return normalized

    def _should_prefer_fallback(self, refined: str, fallback: str) -> bool:
        """Use deterministic fallback when LLM output is too generic."""
        if not self._is_generic_topics_ack(refined):
            return False
        return not self._is_generic_topics_ack(fallback)

    def _is_generic_topics_ack(self, text: str) -> bool:
        return bool(re.search(r"\bon the following (?:topics?|items?|sections?)\b", text, flags=re.IGNORECASE))

    def _should_sample_traceback(self) -> bool:
        """Sample traceback logging deterministically to reduce repetitive noise."""
        if self._traceback_sample_rate <= 0:
            return False
        interval = max(1, round(1.0 / self._traceback_sample_rate))
        return self._error_count % interval == 0
