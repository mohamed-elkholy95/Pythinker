#!/usr/bin/env python3
"""Unit test for LLM wrapper that removes response_format"""

import sys


class MockLLM:
    """Mock LLM that tracks response_format parameter"""

    def __init__(self):
        self.last_invoke_kwargs = {}
        self.last_bind_kwargs = {}
        self.model_kwargs = {"response_format": {"type": "json"}}
        self.default_kwargs = {"response_format": {"type": "json"}}

    async def ainvoke(self, *args, **kwargs):
        self.last_invoke_kwargs = kwargs
        return {"content": "test response"}

    def invoke(self, *args, **kwargs):
        self.last_invoke_kwargs = kwargs
        return {"content": "test response"}

    async def agenerate(self, *args, **kwargs):
        self.last_invoke_kwargs = kwargs
        return {"content": "test response"}

    def generate(self, *args, **kwargs):
        self.last_invoke_kwargs = kwargs
        return {"content": "test response"}

    def bind(self, **kwargs):
        self.last_bind_kwargs = kwargs
        return self


def test_wrapper():
    """Test that the wrapper removes response_format correctly"""

    # Import the wrapper function
    from app.infrastructure.external.browser.browseruse_browser import BrowserUseService

    # Create mock LLM
    mock_llm = MockLLM()

    # Create service instance to access wrapper method
    service = BrowserUseService(cdp_url="http://test:9222")

    # Apply wrapper
    wrapped = service._wrap_llm_for_compatibility(mock_llm)

    # Test 1: Check that response_format was removed from model_kwargs
    if "response_format" in mock_llm.model_kwargs:
        return False

    # Test 2: Check that response_format was removed from default_kwargs
    if "response_format" in mock_llm.default_kwargs:
        return False

    # Test 3: Test invoke with response_format
    wrapped.invoke("test", response_format={"type": "json"}, temperature=0.5)
    if "response_format" in mock_llm.last_invoke_kwargs:
        return False
    if "temperature" not in mock_llm.last_invoke_kwargs:
        return False

    # Test 4: Test async invoke with response_format
    import asyncio

    asyncio.run(wrapped.ainvoke("test", response_format={"type": "json"}, temperature=0.5))
    if "response_format" in mock_llm.last_invoke_kwargs:
        return False
    if "temperature" not in mock_llm.last_invoke_kwargs:
        return False

    # Test 5: Test bind with response_format
    wrapped.bind(response_format={"type": "json"}, temperature=0.7)
    if "response_format" in mock_llm.last_bind_kwargs:
        return False
    if "temperature" not in mock_llm.last_bind_kwargs:
        return False

    # Test 6: Test attribute delegation
    return hasattr(wrapped, "model_kwargs")


if __name__ == "__main__":
    try:
        success = test_wrapper()

        if success:
            pass
        else:
            pass

        sys.exit(0 if success else 1)

    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
