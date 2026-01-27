"""
Coordinated memory management with smart compaction.

Provides intelligent memory compaction that extracts key results
before compacting, and coordinates with token management for
efficient context usage.

Phase 3 Enhancements:
- Proactive compaction triggers based on multiple signals
- LLM-based extraction for unknown tools
- Archive integration for persisting compacted content
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.infrastructure.storage.file_storage import FileStorage

logger = logging.getLogger(__name__)


class PressureLevel(Enum):
    """Token pressure levels for memory management."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"


@dataclass
class PressureStatus:
    """Current token pressure status."""
    level: PressureLevel
    current_tokens: int
    max_tokens: int
    usage_ratio: float

    def to_context_signal(self) -> str:
        """Convert pressure status to context signal for the agent."""
        if self.level == PressureLevel.CRITICAL:
            return f"[CONTEXT PRESSURE: CRITICAL - {self.usage_ratio:.0%} capacity used. Prioritize essential outputs only.]"
        elif self.level == PressureLevel.WARNING:
            return f"[CONTEXT PRESSURE: WARNING - {self.usage_ratio:.0%} capacity used. Consider concise responses.]"
        return ""


@dataclass
class CompactedMessage:
    """Result of message compaction with summary and reference"""
    summary: str
    file_ref: Optional[str] = None
    original_tokens: int = 0
    compacted_tokens: int = 0
    key_results: List[str] = field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.compacted_tokens


@dataclass
class ExtractionResult:
    """Extracted key information from a tool result"""
    success: bool
    key_facts: List[str]
    data_points: Dict[str, Any]
    urls: List[str]
    error_message: Optional[str] = None
    extraction_method: str = "heuristic"  # "heuristic", "llm", or "fallback"
    confidence: float = 1.0  # Confidence score (0.0-1.0)


class MemoryManager:
    """
    Manages memory compaction with intelligent result extraction.

    Instead of simply replacing content with "(compacted)", this manager:
    1. Extracts key facts and results from tool outputs
    2. Preserves success/failure status and important data points
    3. Optionally stores full results in sandbox files for reference
    """

    # Functions whose outputs should be summarized, not just compacted
    SUMMARIZABLE_FUNCTIONS = {
        "browser_view": "browser content",
        "browser_navigate": "navigation result",
        "shell_exec": "command output",
        "file_read": "file content",
        "file_list": "directory listing",
        "info_search_web": "search results",
        "browser_get_content": "page content",
    }

    # Maximum tokens for a compacted summary
    MAX_SUMMARY_TOKENS = 200

    # Default limits for memory management
    DEFAULT_MAX_ARCHIVE_SIZE = 1000  # Maximum entries in archive index
    DEFAULT_ARCHIVE_CLEANUP_BATCH = 100  # Entries to remove when limit exceeded

    def __init__(
        self,
        sandbox_path: str = "/home/ubuntu/.context_archive",
        enable_file_storage: bool = True,
        file_storage: Optional["FileStorage"] = None,
        max_archive_size: int = DEFAULT_MAX_ARCHIVE_SIZE,
        archive_cleanup_batch: int = DEFAULT_ARCHIVE_CLEANUP_BATCH,
    ):
        """
        Initialize the memory manager.

        Args:
            sandbox_path: Path to store archived context in sandbox
            enable_file_storage: Whether to save full content to files
            file_storage: Optional file storage backend for archive persistence
            max_archive_size: Maximum entries in archive index (default 1000)
            archive_cleanup_batch: Entries to remove when limit exceeded (default 100)
        """
        self._sandbox_path = sandbox_path
        self._enable_file_storage = enable_file_storage
        self._file_storage = file_storage
        self._archive_counter = 0
        # Token history for growth rate tracking (proactive compaction)
        self._token_history: List[int] = []
        self._max_history_size = 20
        # Archive index: message_id -> archive_path
        self._archive_index: Dict[str, str] = {}
        # Archive index insertion order for FIFO cleanup
        self._archive_order: List[str] = []
        # Memory limits
        self._max_archive_size = max_archive_size
        self._archive_cleanup_batch = archive_cleanup_batch

    def compact_message(
        self,
        message: Dict[str, Any],
        preserve_summary: bool = True
    ) -> Tuple[Dict[str, Any], CompactedMessage]:
        """
        Compact a message while preserving key information.

        Args:
            message: The message to compact
            preserve_summary: Whether to include summary in compacted content

        Returns:
            Tuple of (compacted message dict, CompactedMessage metadata)
        """
        if message.get("role") != "tool":
            # Only compact tool messages
            return message, CompactedMessage(
                summary="",
                original_tokens=0,
                compacted_tokens=0
            )

        function_name = message.get("function_name", "")
        content = message.get("content", "")

        # Estimate original tokens
        original_tokens = len(content) // 4

        # Already compacted?
        if "(compacted)" in content or "(removed)" in content:
            return message, CompactedMessage(
                summary=content,
                original_tokens=original_tokens,
                compacted_tokens=original_tokens
            )

        # Extract key information
        extraction = self._extract_key_results(function_name, content)

        # Build summary
        if preserve_summary and extraction.key_facts:
            summary_parts = [f"[{function_name}]"]

            if extraction.success:
                summary_parts.append("SUCCESS")
            else:
                summary_parts.append(f"FAILED: {extraction.error_message or 'unknown'}")

            # Add key facts (limit to fit token budget)
            facts_text = " | ".join(extraction.key_facts[:5])
            if len(facts_text) > 500:
                facts_text = facts_text[:497] + "..."
            summary_parts.append(facts_text)

            # Add URL references if any
            if extraction.urls:
                summary_parts.append(f"URLs: {', '.join(extraction.urls[:3])}")

            summary = " - ".join(summary_parts)
        else:
            summary = f"[{function_name}] (compacted)"

        # Create compacted content
        from app.domain.models.tool_result import ToolResult
        compacted_content = ToolResult(
            success=extraction.success,
            data=summary
        ).model_dump_json()

        # Create compacted message
        compacted_message = dict(message)
        compacted_message["content"] = compacted_content

        compacted_tokens = len(compacted_content) // 4

        return compacted_message, CompactedMessage(
            summary=summary,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            key_results=extraction.key_facts,
            file_ref=None  # File storage handled separately
        )

    def _extract_key_results(
        self,
        function_name: str,
        content: str
    ) -> ExtractionResult:
        """
        Extract key information from tool output.

        Args:
            function_name: Name of the tool function
            content: Raw content to extract from

        Returns:
            ExtractionResult with extracted information
        """
        key_facts = []
        data_points = {}
        urls = []
        success = True
        error_message = None

        # Try to parse as JSON (ToolResult format)
        try:
            parsed = json.loads(content)
            success = parsed.get("success", True)
            error_message = parsed.get("message") if not success else None
            data = parsed.get("data", "")

            if isinstance(data, str):
                content_to_analyze = data
            else:
                content_to_analyze = json.dumps(data)
        except json.JSONDecodeError:
            content_to_analyze = content

        # Extract based on function type
        if function_name in ("browser_view", "browser_navigate", "browser_get_content"):
            key_facts, urls = self._extract_browser_results(content_to_analyze)
        elif function_name == "shell_exec":
            key_facts = self._extract_shell_results(content_to_analyze)
        elif function_name == "file_read":
            key_facts = self._extract_file_results(content_to_analyze)
        elif function_name == "info_search_web":
            key_facts, urls = self._extract_search_results(content_to_analyze)
        elif function_name == "file_list":
            key_facts = self._extract_listing_results(content_to_analyze)
        else:
            # Generic extraction
            key_facts = self._extract_generic_results(content_to_analyze)

        return ExtractionResult(
            success=success,
            key_facts=key_facts,
            data_points=data_points,
            urls=urls,
            error_message=error_message
        )

    def _extract_browser_results(self, content: str) -> Tuple[List[str], List[str]]:
        """Extract key facts from browser content"""
        facts = []
        urls = []

        # Extract URLs
        url_pattern = r'https?://[^\s<>"\']+(?:[^\s<>"\'\.,;:!?\)])'
        found_urls = re.findall(url_pattern, content)
        urls = list(set(found_urls))[:5]

        # Extract title if present
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.I)
        if title_match:
            facts.append(f"Title: {title_match.group(1)[:100]}")

        # Count interactive elements
        link_count = len(re.findall(r'<a\s', content, re.I))
        if link_count:
            facts.append(f"{link_count} links found")

        # Check for forms
        if re.search(r'<form', content, re.I):
            facts.append("Contains form")

        # Content length indicator
        word_count = len(content.split())
        if word_count > 100:
            facts.append(f"~{word_count} words")

        return facts, urls

    def _extract_shell_results(self, content: str) -> List[str]:
        """Extract key facts from shell command output"""
        facts = []
        lines = content.strip().split('\n')

        # Check for error indicators
        error_patterns = ['error', 'failed', 'denied', 'not found', 'exception']
        has_error = any(
            pattern in content.lower()
            for pattern in error_patterns
        )

        if has_error:
            # Extract error message
            for line in lines[:5]:
                if any(p in line.lower() for p in error_patterns):
                    facts.append(f"Error: {line[:100]}")
                    break

        # Count output lines
        if len(lines) > 1:
            facts.append(f"{len(lines)} lines output")

        # Check for common outputs
        if 'installed' in content.lower():
            facts.append("Installation completed")
        if 'created' in content.lower():
            facts.append("Created resource")
        if 'success' in content.lower():
            facts.append("Operation successful")

        return facts[:5]

    def _extract_file_results(self, content: str) -> List[str]:
        """Extract key facts from file content"""
        facts = []
        lines = content.strip().split('\n')

        facts.append(f"{len(lines)} lines")

        # Detect file type indicators
        if content.startswith('{') or content.startswith('['):
            facts.append("JSON format")
        elif 'def ' in content or 'import ' in content:
            facts.append("Python code")
        elif '<html' in content.lower() or '<!doctype' in content.lower():
            facts.append("HTML document")
        elif 'function' in content or 'const ' in content:
            facts.append("JavaScript code")

        return facts

    def _extract_search_results(self, content: str) -> Tuple[List[str], List[str]]:
        """Extract key facts from search results"""
        facts = []
        urls = []

        # Try to parse as JSON
        try:
            results = json.loads(content)
            if isinstance(results, list):
                facts.append(f"{len(results)} results found")
                for r in results[:3]:
                    if isinstance(r, dict):
                        title = r.get('title', '')[:50]
                        if title:
                            facts.append(title)
                        url = r.get('url', r.get('link', ''))
                        if url:
                            urls.append(url)
        except json.JSONDecodeError:
            # Count result indicators
            result_count = content.count('http')
            if result_count:
                facts.append(f"~{result_count} results")

        # Extract URLs
        url_pattern = r'https?://[^\s<>"\']+(?:[^\s<>"\'\.,;:!?\)])'
        found_urls = re.findall(url_pattern, content)
        urls.extend(found_urls[:5])
        urls = list(set(urls))[:5]

        return facts[:5], urls

    def _extract_listing_results(self, content: str) -> List[str]:
        """Extract key facts from directory listing"""
        facts = []
        lines = content.strip().split('\n')

        facts.append(f"{len(lines)} items")

        # Count file types
        dirs = sum(1 for l in lines if l.endswith('/') or 'dir' in l.lower())
        if dirs:
            facts.append(f"{dirs} directories")

        return facts

    def _extract_generic_results(self, content: str) -> List[str]:
        """Extract key facts from generic content"""
        facts = []

        # Basic metrics
        word_count = len(content.split())
        line_count = len(content.split('\n'))

        if word_count > 0:
            facts.append(f"{word_count} words, {line_count} lines")

        # Check for success/failure indicators
        if 'success' in content.lower():
            facts.append("Indicates success")
        elif 'error' in content.lower() or 'failed' in content.lower():
            facts.append("Contains errors")

        return facts[:3]

    def compact_messages_batch(
        self,
        messages: List[Dict[str, Any]],
        preserve_recent: int = 10,
        token_threshold: int = 80000
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Compact a batch of messages based on token threshold.

        Args:
            messages: List of messages to compact
            preserve_recent: Number of recent messages to preserve
            token_threshold: Token threshold to trigger compaction

        Returns:
            Tuple of (compacted messages, tokens saved)
        """
        # Calculate current tokens
        total_tokens = sum(len(str(m.get("content", ""))) // 4 for m in messages)

        if total_tokens < token_threshold:
            return messages, 0

        logger.info(f"Compacting messages: {total_tokens} tokens, threshold: {token_threshold}")

        tokens_saved = 0
        compacted_messages = []
        compact_until = len(messages) - preserve_recent

        for i, msg in enumerate(messages):
            if i < compact_until and msg.get("role") == "tool":
                function_name = msg.get("function_name", "")
                if function_name in self.SUMMARIZABLE_FUNCTIONS:
                    compacted_msg, metadata = self.compact_message(msg)
                    compacted_messages.append(compacted_msg)
                    tokens_saved += metadata.tokens_saved
                    continue

            compacted_messages.append(msg)

        logger.info(f"Compaction complete: saved {tokens_saved} tokens")
        return compacted_messages, tokens_saved

    def get_archive_path(self, function_name: str) -> str:
        """Generate unique archive file path"""
        self._archive_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self._sandbox_path}/{function_name}_{timestamp}_{self._archive_counter}.txt"

    # =========================================================================
    # Phase 3: Proactive Compaction Triggers
    # =========================================================================

    def track_token_usage(self, current_tokens: int) -> None:
        """
        Track token usage for growth rate analysis.

        Args:
            current_tokens: Current token count in context
        """
        self._token_history.append(current_tokens)
        # Keep only recent history
        if len(self._token_history) > self._max_history_size:
            self._token_history = self._token_history[-self._max_history_size:]

    def should_trigger_compaction(
        self,
        pressure: PressureStatus,
        recent_tools: List[str],
        iteration_count: int
    ) -> Tuple[bool, str]:
        """
        Determine if compaction should be triggered with reason.

        Evaluates multiple signals to proactively trigger compaction
        before hitting hard limits.

        Args:
            pressure: Current token pressure status
            recent_tools: List of recently used tool names
            iteration_count: Current iteration number

        Returns:
            Tuple of (should_compact, reason)
        """
        # Rule 1: Critical pressure - immediate compaction
        if pressure.level in [PressureLevel.CRITICAL, PressureLevel.OVERFLOW]:
            return True, f"Token pressure at {pressure.level.value}"

        # Rule 2: Verbose tool output accumulation
        verbose_tools = {"browser_view", "shell_exec", "file_read", "browser_get_content"}
        recent_verbose = sum(1 for t in recent_tools[-5:] if t in verbose_tools)
        if recent_verbose >= 3 and pressure.level == PressureLevel.WARNING:
            return True, "Multiple verbose tool outputs detected"

        # Rule 3: Periodic compaction at regular intervals
        if iteration_count > 0 and iteration_count % 20 == 0:
            if pressure.level != PressureLevel.NORMAL:
                return True, f"Periodic compaction at iteration {iteration_count}"

        # Rule 4: High memory growth rate
        if len(self._token_history) >= 5:
            growth_rate = (self._token_history[-1] - self._token_history[-5]) / 5
            if growth_rate > 1000:  # >1000 tokens per iteration average
                return True, f"High memory growth rate: {growth_rate:.0f} tokens/iteration"

        # Rule 5: Approaching warning threshold with upward trend
        if pressure.level == PressureLevel.NORMAL and pressure.usage_ratio > 0.6:
            if len(self._token_history) >= 3:
                # Check if trending upward
                recent_trend = self._token_history[-1] - self._token_history[-3]
                if recent_trend > 2000:
                    return True, "Approaching threshold with upward trend"

        return False, ""

    def get_pressure_status(
        self,
        current_tokens: int,
        max_tokens: int = 128000
    ) -> PressureStatus:
        """
        Calculate current token pressure status.

        Args:
            current_tokens: Current token count
            max_tokens: Maximum token capacity

        Returns:
            PressureStatus with level and details
        """
        usage_ratio = current_tokens / max_tokens

        if usage_ratio >= 0.95:
            level = PressureLevel.OVERFLOW
        elif usage_ratio >= 0.85:
            level = PressureLevel.CRITICAL
        elif usage_ratio >= 0.70:
            level = PressureLevel.WARNING
        else:
            level = PressureLevel.NORMAL

        return PressureStatus(
            level=level,
            current_tokens=current_tokens,
            max_tokens=max_tokens,
            usage_ratio=usage_ratio
        )

    # =========================================================================
    # Phase 3: LLM-Based Extraction for Unknown Tools
    # =========================================================================

    async def extract_with_llm(
        self,
        function_name: str,
        content: str,
        llm: "LLM"
    ) -> ExtractionResult:
        """
        Use LLM to extract key information from unknown tool output.

        Falls back to heuristic extraction if LLM fails or for known tools.

        Args:
            function_name: Name of the tool function
            content: Raw tool output content
            llm: LLM instance for extraction

        Returns:
            ExtractionResult with extracted information
        """
        # For known tools, use existing extractors
        if function_name in self.SUMMARIZABLE_FUNCTIONS:
            result = self._extract_key_results(function_name, content)
            result.extraction_method = "heuristic"
            result.confidence = 1.0
            return result

        # LLM extraction for unknown tools
        prompt = f"""Extract key information from this tool output.

Tool: {function_name}
Output:
{content[:4000]}

Provide a concise summary (max 200 words) that preserves:
1. Success/failure status
2. Key data or results
3. Any URLs, paths, or identifiers
4. Error messages if present

Format your response as:
STATUS: success/failure
KEY_FACTS:
- fact 1
- fact 2
URLS: (if any)
- url 1
ERRORS: (if any)"""

        try:
            response = await llm.ask(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )

            # Parse LLM response
            response_text = response.content if hasattr(response, 'content') else str(response)
            key_facts = self._parse_llm_extraction(response_text)
            success = "success" in response_text.lower() and "failure" not in response_text.lower()

            return ExtractionResult(
                success=success,
                key_facts=key_facts,
                data_points={},
                urls=self._extract_urls_from_text(response_text),
                extraction_method="llm",
                confidence=0.8
            )
        except Exception as e:
            logger.warning(f"LLM extraction failed for {function_name}: {e}")
            return self._fallback_extraction(function_name, content)

    def _parse_llm_extraction(self, response: str) -> List[str]:
        """Parse LLM extraction response into key facts."""
        facts = []
        lines = response.strip().split('\n')

        in_facts_section = False
        for line in lines:
            line = line.strip()
            if line.startswith('KEY_FACTS:'):
                in_facts_section = True
                continue
            if line.startswith('URLS:') or line.startswith('ERRORS:'):
                in_facts_section = False
            if in_facts_section and line.startswith('- '):
                facts.append(line[2:].strip())

        # Fallback: take non-empty lines if no structured facts found
        if not facts:
            facts = [line.strip() for line in lines if line.strip() and len(line) < 200][:5]

        return facts[:5]

    def _extract_urls_from_text(self, text: str) -> List[str]:
        """Extract URLs from text."""
        url_pattern = r'https?://[^\s<>"\']+(?:[^\s<>"\'\.,;:!?\)])'
        return list(set(re.findall(url_pattern, text)))[:5]

    def _fallback_extraction(
        self,
        function_name: str,
        content: str
    ) -> ExtractionResult:
        """
        Fallback extraction using heuristics when LLM fails.

        Args:
            function_name: Name of the tool function
            content: Raw content to extract from

        Returns:
            ExtractionResult with basic extracted information
        """
        # Take first 500 and last 200 chars for long content
        if len(content) > 700:
            summary = content[:500] + "\n...\n" + content[-200:]
        else:
            summary = content

        # Infer success from content
        success = not any(
            indicator in content.lower()
            for indicator in ['error', 'failed', 'exception', 'denied']
        )

        return ExtractionResult(
            success=success,
            key_facts=[f"[{function_name}] {summary[:200]}..."],
            data_points={},
            urls=self._extract_urls_from_text(content),
            error_message=None if success else "Possible error detected",
            extraction_method="fallback",
            confidence=0.5
        )

    # =========================================================================
    # Phase 3: Archive Integration
    # =========================================================================

    async def compact_and_archive(
        self,
        message: Dict[str, Any],
        session_id: str
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Compact message and archive full content to storage.

        Args:
            message: The message to compact
            session_id: Current session identifier

        Returns:
            Tuple of (compacted message dict, archive path or None)
        """
        # Extract content for compaction
        content = message.get("content", "")
        function_name = message.get("function_name", "")

        if not content or len(content) < 500:
            return message, None  # Don't compact small messages

        # Extract key information
        extraction = self._extract_key_results(function_name, content)

        # Generate archive path
        message_id = message.get("id", str(uuid.uuid4()))
        archive_path = f"/archives/{session_id}/{message_id}.json"

        # Archive full content if storage is enabled and available
        if self._enable_file_storage and self._file_storage:
            try:
                archive_data = json.dumps({
                    "message_id": message_id,
                    "function_name": function_name,
                    "original_content": content,
                    "archived_at": datetime.now().isoformat(),
                    "extraction_method": extraction.extraction_method,
                    "key_facts": extraction.key_facts,
                    "urls": extraction.urls,
                })
                await self._file_storage.write(archive_path, archive_data)
                self._add_to_archive_index(message_id, archive_path)
                logger.debug(f"Archived message {message_id} to {archive_path}")
            except Exception as e:
                logger.warning(f"Failed to archive message {message_id}: {e}")
                archive_path = None
        else:
            # Store in memory index only
            self._add_to_archive_index(message_id, f"memory://{message_id}")
            archive_path = None

        # Build summary for compacted message
        summary_parts = [f"[{function_name}]"]
        if extraction.success:
            summary_parts.append("SUCCESS")
        else:
            summary_parts.append(f"FAILED: {extraction.error_message or 'unknown'}")

        facts_text = " | ".join(extraction.key_facts[:5])
        if len(facts_text) > 500:
            facts_text = facts_text[:497] + "..."
        summary_parts.append(facts_text)

        if extraction.urls:
            summary_parts.append(f"URLs: {', '.join(extraction.urls[:3])}")

        summary = " - ".join(summary_parts)

        # Create compacted message
        from app.domain.models.tool_result import ToolResult
        compacted_content = ToolResult(
            success=extraction.success,
            data=summary
        ).model_dump_json()

        compacted_message = dict(message)
        compacted_message["content"] = compacted_content
        compacted_message["_compacted"] = True
        compacted_message["_archive_path"] = archive_path

        return compacted_message, archive_path

    async def retrieve_archived(self, message_id: str) -> Optional[str]:
        """
        Retrieve original content from archive.

        Args:
            message_id: ID of the message to retrieve

        Returns:
            Original content or None if not found
        """
        archive_path = self._archive_index.get(message_id)
        if not archive_path:
            logger.debug(f"No archive found for message {message_id}")
            return None

        # Memory-only archive (no file storage)
        if archive_path.startswith("memory://"):
            logger.debug(f"Message {message_id} was archived in memory only")
            return None

        if not self._file_storage:
            logger.warning(f"File storage not configured, cannot retrieve {message_id}")
            return None

        try:
            archived = await self._file_storage.read(archive_path)
            data = json.loads(archived)
            return data.get("original_content")
        except Exception as e:
            logger.error(f"Failed to retrieve archive for {message_id}: {e}")
            return None

    def get_archive_stats(self) -> Dict[str, Any]:
        """
        Get statistics about archived content.

        Returns:
            Dictionary with archive statistics
        """
        return {
            "total_archived": len(self._archive_index),
            "max_archive_size": self._max_archive_size,
            "archive_usage_ratio": len(self._archive_index) / self._max_archive_size if self._max_archive_size > 0 else 0,
            "file_archived": sum(
                1 for p in self._archive_index.values()
                if not p.startswith("memory://")
            ),
            "memory_only": sum(
                1 for p in self._archive_index.values()
                if p.startswith("memory://")
            ),
            "token_history_size": len(self._token_history),
            "last_token_count": self._token_history[-1] if self._token_history else 0,
        }

    def _enforce_archive_limit(self) -> int:
        """
        Enforce archive size limit by removing oldest entries (FIFO).

        Returns:
            Number of entries removed
        """
        if len(self._archive_index) <= self._max_archive_size:
            return 0

        # Calculate how many to remove
        excess = len(self._archive_index) - self._max_archive_size
        to_remove = max(excess, self._archive_cleanup_batch)

        # Remove oldest entries (FIFO based on insertion order)
        removed = 0
        while self._archive_order and removed < to_remove:
            message_id = self._archive_order.pop(0)
            if message_id in self._archive_index:
                del self._archive_index[message_id]
                removed += 1

        if removed > 0:
            logger.info(f"Archive cleanup: removed {removed} oldest entries (archive size: {len(self._archive_index)})")

        return removed

    def cleanup_archive(self, max_entries: Optional[int] = None) -> int:
        """
        Manually clean up the archive index to free memory.

        Args:
            max_entries: Maximum entries to keep (uses default if None)

        Returns:
            Number of entries removed
        """
        if max_entries is not None:
            original_max = self._max_archive_size
            self._max_archive_size = max_entries
            removed = self._enforce_archive_limit()
            self._max_archive_size = original_max
        else:
            removed = self._enforce_archive_limit()

        return removed

    def clear_archive(self) -> int:
        """
        Clear all entries from the archive index.

        Returns:
            Number of entries cleared
        """
        count = len(self._archive_index)
        self._archive_index.clear()
        self._archive_order.clear()
        logger.info(f"Archive cleared: removed {count} entries")
        return count

    def _add_to_archive_index(self, message_id: str, archive_path: str) -> None:
        """
        Add an entry to the archive index with automatic cleanup.

        Args:
            message_id: Unique identifier for the message
            archive_path: Path where the message is archived
        """
        # Add to index and order tracking
        if message_id not in self._archive_index:
            self._archive_order.append(message_id)
        self._archive_index[message_id] = archive_path

        # Enforce limit
        self._enforce_archive_limit()


# Singleton for global access
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
