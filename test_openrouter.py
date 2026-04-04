#!/usr/bin/env python3
"""Test OpenRouter configuration"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.config import get_settings


def test_openrouter_config():
    """Test OpenRouter configuration"""
    settings = get_settings()

    print("=" * 60)
    print("OpenRouter Configuration Test")
    print("=" * 60)
    print(f"LLM Provider: {settings.llm_provider}")
    print(f"API Base: {settings.api_base}")
    print(f"Model Name: {settings.model_name}")
    print(f"Temperature: {settings.temperature}")
    print(f"Max Tokens: {settings.max_tokens}")
    if settings.api_key:
        print(f"API Key: Set (redacted, length={len(settings.api_key)})")
    else:
        print("API Key: Not set")
    print("=" * 60)

    # Verify OpenRouter settings
    if settings.llm_provider != "openai":
        print(
            f"❌ ERROR: LLM provider should be 'openai', got '{settings.llm_provider}'"
        )
        return False

    if "openrouter.ai" not in settings.api_base:
        print(
            f"❌ ERROR: API base should contain 'openrouter.ai', got '{settings.api_base}'"
        )
        return False

    if "nemotron" not in settings.model_name.lower():
        print(
            f"⚠️  WARNING: Model name doesn't contain 'nemotron', got '{settings.model_name}'"
        )

    if not settings.api_key or not settings.api_key.startswith("sk-or-v1-"):
        print("❌ ERROR: OpenRouter API key should start with 'sk-or-v1-'")
        return False

    print("✅ OpenRouter configuration is correct!")
    print()
    print("Now testing LLM initialization...")

    # Test LLM initialization
    try:
        from app.infrastructure.external.llm.factory import get_llm_from_factory

        llm = get_llm_from_factory()
        if llm is None:
            print("❌ ERROR: Failed to initialize LLM")
            return False
        print(f"✅ LLM initialized successfully: {type(llm).__name__}")

        # Test a simple completion
        print()
        print("Testing simple completion...")
        response = llm.complete("Say 'Hello from OpenRouter!' and nothing else.")
        print(f"✅ LLM Response: {response}")
        return True
    except Exception as e:
        print(f"❌ ERROR initializing LLM: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_openrouter_config()
    sys.exit(0 if success else 1)
