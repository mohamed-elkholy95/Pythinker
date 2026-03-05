from typing import Any, Protocol


class JsonParser(Protocol):
    """Json parser interface"""

    async def parse(
        self,
        text: str,
        default_value: Any | None = None,
        tier: str | None = None,
        allow_llm_json_repair: bool | None = None,
    ) -> dict | list | Any:
        """
        Parse LLM output string to JSON using multiple strategies.
        Falls back to LLM parsing if local strategies fail.

        Args:
            text: The raw string output from LLM
            default_value: Default value to return if parsing fails
            tier: Optional output reliability tier (A/B/C) for stage gating
            allow_llm_json_repair: Optional explicit override for stage-5 LLM repair

        Returns:
            Parsed JSON object (dict, list, or other JSON-serializable type)

        Raises:
            ValueError: If all parsing strategies fail and no default value provided
        """
