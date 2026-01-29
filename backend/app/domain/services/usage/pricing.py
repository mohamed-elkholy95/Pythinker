"""Model pricing configuration and cost calculation utilities.

Pricing is per 1 million tokens (1M tokens).
"""
import re
from dataclasses import dataclass


@dataclass
class ModelPricing:
    """Pricing information for an LLM model.

    All prices are in USD per 1 million tokens.
    """
    prompt_price: float  # Price per 1M prompt tokens
    completion_price: float  # Price per 1M completion tokens
    cached_price: float | None = None  # Price per 1M cached tokens (Anthropic)

    def calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0
    ) -> tuple[float, float, float]:
        """Calculate cost for token usage.

        Returns:
            Tuple of (prompt_cost, completion_cost, total_cost)
        """
        prompt_cost = (prompt_tokens / 1_000_000) * self.prompt_price
        completion_cost = (completion_tokens / 1_000_000) * self.completion_price

        # If cached tokens are provided and we have cached pricing
        if cached_tokens > 0 and self.cached_price is not None:
            # Cached tokens replace some prompt tokens at reduced rate
            cached_cost = (cached_tokens / 1_000_000) * self.cached_price
            # Adjust prompt cost: cached tokens were already counted in prompt_tokens
            # but should be charged at cached_price instead
            prompt_cost = ((prompt_tokens - cached_tokens) / 1_000_000) * self.prompt_price
            prompt_cost += cached_cost

        total_cost = prompt_cost + completion_cost
        return prompt_cost, completion_cost, total_cost


# Model pricing database
# Prices as of January 2025 - update as pricing changes
MODEL_PRICING: dict[str, ModelPricing] = {
    # =========================================
    # OpenAI Models
    # =========================================
    # GPT-4o series
    "gpt-4o": ModelPricing(2.50, 10.0, 1.25),
    "gpt-4o-2024-11-20": ModelPricing(2.50, 10.0, 1.25),
    "gpt-4o-2024-08-06": ModelPricing(2.50, 10.0, 1.25),
    "gpt-4o-2024-05-13": ModelPricing(5.0, 15.0, None),

    # GPT-4o-mini series
    "gpt-4o-mini": ModelPricing(0.15, 0.60, 0.075),
    "gpt-4o-mini-2024-07-18": ModelPricing(0.15, 0.60, 0.075),

    # GPT-4 Turbo
    "gpt-4-turbo": ModelPricing(10.0, 30.0, None),
    "gpt-4-turbo-2024-04-09": ModelPricing(10.0, 30.0, None),
    "gpt-4-turbo-preview": ModelPricing(10.0, 30.0, None),

    # GPT-4
    "gpt-4": ModelPricing(30.0, 60.0, None),
    "gpt-4-0613": ModelPricing(30.0, 60.0, None),
    "gpt-4-32k": ModelPricing(60.0, 120.0, None),

    # GPT-3.5 Turbo
    "gpt-3.5-turbo": ModelPricing(0.50, 1.50, None),
    "gpt-3.5-turbo-0125": ModelPricing(0.50, 1.50, None),
    "gpt-3.5-turbo-1106": ModelPricing(1.0, 2.0, None),

    # o1 reasoning models
    "o1": ModelPricing(15.0, 60.0, 7.50),
    "o1-2024-12-17": ModelPricing(15.0, 60.0, 7.50),
    "o1-preview": ModelPricing(15.0, 60.0, None),
    "o1-mini": ModelPricing(3.0, 12.0, 1.50),
    "o1-mini-2024-09-12": ModelPricing(3.0, 12.0, 1.50),
    "o3-mini": ModelPricing(1.10, 4.40, 0.55),

    # =========================================
    # Anthropic Models
    # =========================================
    # Claude 4 series (Opus 4 / Sonnet 4)
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0, 0.30),
    "claude-opus-4-20250514": ModelPricing(15.0, 75.0, 1.50),

    # Claude 3.5 series
    "claude-3-5-sonnet-20241022": ModelPricing(3.0, 15.0, 0.30),
    "claude-3-5-sonnet-latest": ModelPricing(3.0, 15.0, 0.30),
    "claude-3-5-sonnet-20240620": ModelPricing(3.0, 15.0, 0.30),
    "claude-3-5-haiku-20241022": ModelPricing(0.80, 4.0, 0.08),
    "claude-3-5-haiku-latest": ModelPricing(0.80, 4.0, 0.08),

    # Claude 3 series
    "claude-3-opus-20240229": ModelPricing(15.0, 75.0, 1.50),
    "claude-3-opus-latest": ModelPricing(15.0, 75.0, 1.50),
    "claude-3-sonnet-20240229": ModelPricing(3.0, 15.0, 0.30),
    "claude-3-haiku-20240307": ModelPricing(0.25, 1.25, 0.03),

    # =========================================
    # DeepSeek Models
    # =========================================
    "deepseek-chat": ModelPricing(0.14, 0.28, 0.014),
    "deepseek-reasoner": ModelPricing(0.55, 2.19, 0.14),

    # =========================================
    # Google Models
    # =========================================
    "gemini-1.5-pro": ModelPricing(1.25, 5.0, None),
    "gemini-1.5-flash": ModelPricing(0.075, 0.30, None),
    "gemini-2.0-flash": ModelPricing(0.10, 0.40, None),

    # =========================================
    # Local/Free Models (Ollama, etc.)
    # =========================================
    "llama3.2": ModelPricing(0.0, 0.0, None),
    "llama3.1": ModelPricing(0.0, 0.0, None),
    "llama3": ModelPricing(0.0, 0.0, None),
    "llama2": ModelPricing(0.0, 0.0, None),
    "mistral": ModelPricing(0.0, 0.0, None),
    "mixtral": ModelPricing(0.0, 0.0, None),
    "codellama": ModelPricing(0.0, 0.0, None),
    "phi3": ModelPricing(0.0, 0.0, None),
    "qwen2.5": ModelPricing(0.0, 0.0, None),
    "qwen2.5-coder": ModelPricing(0.0, 0.0, None),
}

# Default pricing for unknown models (conservative estimate)
DEFAULT_PRICING = ModelPricing(5.0, 15.0, None)


def get_model_pricing(model_name: str) -> ModelPricing:
    """Get pricing for a model by name.

    Attempts exact match first, then fuzzy matching for model variants.

    Args:
        model_name: The model name/ID

    Returns:
        ModelPricing for the model, or DEFAULT_PRICING if not found
    """
    # Normalize model name
    model_lower = model_name.lower().strip()

    # Exact match
    if model_lower in MODEL_PRICING:
        return MODEL_PRICING[model_lower]

    # Try case-insensitive exact match
    for key, pricing in MODEL_PRICING.items():
        if key.lower() == model_lower:
            return pricing

    # Fuzzy matching for model variants
    # Match base model names (e.g., "gpt-4o-some-custom" -> "gpt-4o")
    patterns = [
        (r"^gpt-4o-mini", "gpt-4o-mini"),
        (r"^gpt-4o", "gpt-4o"),
        (r"^gpt-4-turbo", "gpt-4-turbo"),
        (r"^gpt-4-32k", "gpt-4-32k"),
        (r"^gpt-4", "gpt-4"),
        (r"^gpt-3\.5-turbo", "gpt-3.5-turbo"),
        (r"^o1-mini", "o1-mini"),
        (r"^o1", "o1"),
        (r"^o3-mini", "o3-mini"),
        (r"^claude-sonnet-4", "claude-sonnet-4-20250514"),
        (r"^claude-opus-4", "claude-opus-4-20250514"),
        (r"^claude-3-5-sonnet", "claude-3-5-sonnet-20241022"),
        (r"^claude-3-5-haiku", "claude-3-5-haiku-20241022"),
        (r"^claude-3-opus", "claude-3-opus-20240229"),
        (r"^claude-3-sonnet", "claude-3-sonnet-20240229"),
        (r"^claude-3-haiku", "claude-3-haiku-20240307"),
        (r"^deepseek-chat", "deepseek-chat"),
        (r"^deepseek-reasoner", "deepseek-reasoner"),
        (r"^gemini-2\.0-flash", "gemini-2.0-flash"),
        (r"^gemini-1\.5-pro", "gemini-1.5-pro"),
        (r"^gemini-1\.5-flash", "gemini-1.5-flash"),
        (r"^llama3\.2", "llama3.2"),
        (r"^llama3\.1", "llama3.1"),
        (r"^llama3", "llama3"),
        (r"^llama2", "llama2"),
        (r"^mistral", "mistral"),
        (r"^mixtral", "mixtral"),
        (r"^codellama", "codellama"),
        (r"^phi", "phi3"),
        (r"^qwen2\.5-coder", "qwen2.5-coder"),
        (r"^qwen2\.5", "qwen2.5"),
    ]

    for pattern, base_model in patterns:
        if re.match(pattern, model_lower):
            if base_model in MODEL_PRICING:
                return MODEL_PRICING[base_model]

    # Check if it looks like a local/ollama model (no known provider prefix)
    if not any(model_lower.startswith(p) for p in ["gpt-", "claude-", "o1", "gemini-", "deepseek-"]):
        # Assume local model = free
        return ModelPricing(0.0, 0.0, None)

    return DEFAULT_PRICING


def calculate_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0
) -> tuple[float, float, float]:
    """Calculate cost for token usage with automatic model pricing lookup.

    Args:
        model_name: The model name/ID
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cached_tokens: Number of cached prompt tokens (Anthropic)

    Returns:
        Tuple of (prompt_cost, completion_cost, total_cost) in USD
    """
    pricing = get_model_pricing(model_name)
    return pricing.calculate_cost(prompt_tokens, completion_tokens, cached_tokens)


def get_provider_from_model(model_name: str) -> str:
    """Infer provider from model name.

    Args:
        model_name: The model name/ID

    Returns:
        Provider string: "openai", "anthropic", "google", "deepseek", "ollama"
    """
    model_lower = model_name.lower()

    if model_lower.startswith(("gpt-", "o1", "o3")):
        return "openai"
    if model_lower.startswith("claude"):
        return "anthropic"
    if model_lower.startswith("gemini"):
        return "google"
    if model_lower.startswith("deepseek"):
        return "deepseek"
    # Assume local/ollama for unrecognized models
    return "ollama"
