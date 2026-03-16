"""Tool Argument Canonicalization Service

Maps argument aliases to canonical names before Pydantic validation.
"""

import logging
from typing import Any, ClassVar

from app.domain.metrics.agent_metrics import get_agent_metrics

logger = logging.getLogger(__name__)


class ArgumentCanonicalizer:
    """Service for canonicalizing tool argument aliases.

    Implements:
    - Alias mapping registry
    - Per-tool canonicalization rules
    - Security-safe handling (no broad coercion)
    - Metrics tracking
    """

    # Canonicalization rules: {tool_name: {canonical_name: [aliases]}}
    ALIAS_RULES: ClassVar[dict[str, dict[str, list[str]]]] = {
        "browser": {
            "url": ["uri", "link", "address", "web_url"],
            "timeout": ["timeout_ms", "wait_time", "timeout_seconds"],
            "wait_for": ["wait_for_selector", "selector"],
        },
        "file_read": {
            "file_path": ["path", "filepath", "file", "filename"],
            "encoding": ["enc", "charset"],
        },
        "search": {
            "query": ["q", "search_query", "search_term", "term"],
            "max_results": ["limit", "max", "count", "top"],
        },
    }

    def __init__(self):
        """Initialize argument canonicalizer."""
        self._canonicalization_cache: dict[str, dict[str, str]] = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self) -> None:
        """Build reverse mapping from alias -> canonical for fast lookup."""
        for tool_name, canonical_rules in self.ALIAS_RULES.items():
            tool_cache: dict[str, str] = {}

            for canonical_name, aliases in canonical_rules.items():
                for alias in aliases:
                    tool_cache[alias] = canonical_name

            self._canonicalization_cache[tool_name] = tool_cache

    def canonicalize(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize tool arguments.

        Args:
            tool_name: Name of the tool
            args: Arguments to canonicalize

        Returns:
            dict: Canonicalized arguments
        """
        if tool_name not in self._canonicalization_cache:
            # No rules for this tool, return as-is
            return args

        canonical_args: dict[str, Any] = {}
        alias_mapping = self._canonicalization_cache[tool_name]

        for arg_name, arg_value in args.items():
            if arg_name in alias_mapping:
                # Found alias, map to canonical name
                canonical_name = alias_mapping[arg_name]

                logger.info(f"Canonicalized argument: {tool_name}.{arg_name} → {canonical_name}")

                # Track metric
                get_agent_metrics().tool_args_canonicalized.inc(
                    labels={
                        "tool_name": tool_name,
                        "alias_type": arg_name,
                    }
                )

                canonical_args[canonical_name] = arg_value
            else:
                # Not an alias, keep as-is
                canonical_args[arg_name] = arg_value

        return canonical_args

    def validate_no_unknown_fields(
        self,
        tool_name: str,
        args: dict[str, Any],
        known_fields: set[str],
    ) -> tuple[bool, list[str]]:
        """Validate that all arguments are known (after canonicalization).

        Args:
            tool_name: Name of the tool
            args: Canonicalized arguments
            known_fields: Set of known canonical field names

        Returns:
            tuple[bool, list[str]]: (valid, list of unknown fields)
        """
        unknown_fields = [field_name for field_name in args if field_name not in known_fields]

        if unknown_fields:
            logger.warning(f"Unknown fields for {tool_name}: {unknown_fields}")

            # Track rejection metric
            metrics = get_agent_metrics()
            for _field in unknown_fields:
                metrics.tool_args_rejected.inc(
                    labels={
                        "tool_name": tool_name,
                        "rejection_reason": "unknown_field",
                    }
                )

            return False, unknown_fields

        return True, []

    def get_canonical_name(self, tool_name: str, arg_name: str) -> str:
        """Get canonical name for an argument.

        Args:
            tool_name: Name of the tool
            arg_name: Argument name (may be alias)

        Returns:
            str: Canonical name (or original if not an alias)
        """
        if tool_name not in self._canonicalization_cache:
            return arg_name

        alias_mapping = self._canonicalization_cache[tool_name]
        return alias_mapping.get(arg_name, arg_name)

    def add_alias_rule(
        self,
        tool_name: str,
        canonical_name: str,
        aliases: list[str],
    ) -> None:
        """Add new alias rule (for dynamic registration).

        Args:
            tool_name: Name of the tool
            canonical_name: Canonical argument name
            aliases: List of aliases for this argument
        """
        if tool_name not in self.ALIAS_RULES:
            self.ALIAS_RULES[tool_name] = {}

        self.ALIAS_RULES[tool_name][canonical_name] = aliases

        # Rebuild reverse mapping
        self._build_reverse_mapping()

        logger.info(f"Added alias rule: {tool_name}.{canonical_name} ← {aliases}")
