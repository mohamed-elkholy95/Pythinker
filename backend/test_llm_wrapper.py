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
    print("=" * 80)
    print("Testing LLM Wrapper for response_format removal")
    print("=" * 80)

    # Import the wrapper function
    from app.infrastructure.external.browser.browseruse_browser import BrowserUseService

    # Create mock LLM
    mock_llm = MockLLM()
    print(f"✅ Created mock LLM with response_format in model_kwargs: {mock_llm.model_kwargs}")

    # Create service instance to access wrapper method
    service = BrowserUseService(cdp_url="http://test:9222")

    # Apply wrapper
    wrapped = service._wrap_llm_for_compatibility(mock_llm)
    print("✅ Applied LLM wrapper")

    # Test 1: Check that response_format was removed from model_kwargs
    print("\nTest 1: Check model_kwargs cleanup")
    if "response_format" in mock_llm.model_kwargs:
        print("❌ FAILED: response_format still in model_kwargs")
        return False
    print("✅ PASSED: response_format removed from model_kwargs")

    # Test 2: Check that response_format was removed from default_kwargs
    print("\nTest 2: Check default_kwargs cleanup")
    if "response_format" in mock_llm.default_kwargs:
        print("❌ FAILED: response_format still in default_kwargs")
        return False
    print("✅ PASSED: response_format removed from default_kwargs")

    # Test 3: Test invoke with response_format
    print("\nTest 3: Test sync invoke with response_format")
    wrapped.invoke("test", response_format={"type": "json"}, temperature=0.5)
    if "response_format" in mock_llm.last_invoke_kwargs:
        print(f"❌ FAILED: response_format passed to underlying LLM: {mock_llm.last_invoke_kwargs}")
        return False
    if "temperature" not in mock_llm.last_invoke_kwargs:
        print("❌ FAILED: Other kwargs were also removed")
        return False
    print(f"✅ PASSED: response_format removed, other kwargs preserved: {mock_llm.last_invoke_kwargs}")

    # Test 4: Test async invoke with response_format
    print("\nTest 4: Test async invoke with response_format")
    import asyncio
    asyncio.run(wrapped.ainvoke("test", response_format={"type": "json"}, temperature=0.5))
    if "response_format" in mock_llm.last_invoke_kwargs:
        print(f"❌ FAILED: response_format passed to underlying LLM: {mock_llm.last_invoke_kwargs}")
        return False
    if "temperature" not in mock_llm.last_invoke_kwargs:
        print("❌ FAILED: Other kwargs were also removed")
        return False
    print(f"✅ PASSED: response_format removed, other kwargs preserved: {mock_llm.last_invoke_kwargs}")

    # Test 5: Test bind with response_format
    print("\nTest 5: Test bind with response_format")
    wrapped.bind(response_format={"type": "json"}, temperature=0.7)
    if "response_format" in mock_llm.last_bind_kwargs:
        print(f"❌ FAILED: response_format passed to bind: {mock_llm.last_bind_kwargs}")
        return False
    if "temperature" not in mock_llm.last_bind_kwargs:
        print("❌ FAILED: Other kwargs were also removed from bind")
        return False
    print(f"✅ PASSED: response_format removed from bind, other kwargs preserved: {mock_llm.last_bind_kwargs}")

    # Test 6: Test attribute delegation
    print("\nTest 6: Test attribute delegation")
    if not hasattr(wrapped, "model_kwargs"):
        print("❌ FAILED: Wrapper doesn't delegate attributes")
        return False
    print("✅ PASSED: Wrapper delegates attributes to underlying LLM")

    return True


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("LLM Wrapper Unit Test")
    print("=" * 80 + "\n")

    try:
        success = test_wrapper()

        print("\n" + "=" * 80)
        if success:
            print("✅ ALL TESTS PASSED - LLM wrapper is working correctly!")
        else:
            print("❌ TESTS FAILED - LLM wrapper has issues")
        print("=" * 80 + "\n")

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
