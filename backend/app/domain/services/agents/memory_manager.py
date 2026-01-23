"""
Coordinated memory management with smart compaction.

Provides intelligent memory compaction that extracts key results
before compacting, and coordinates with token management for
efficient context usage.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        sandbox_path: str = "/home/ubuntu/.context_archive",
        enable_file_storage: bool = True
    ):
        """
        Initialize the memory manager.

        Args:
            sandbox_path: Path to store archived context in sandbox
            enable_file_storage: Whether to save full content to files
        """
        self._sandbox_path = sandbox_path
        self._enable_file_storage = enable_file_storage
        self._archive_counter = 0

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


# Singleton for global access
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
