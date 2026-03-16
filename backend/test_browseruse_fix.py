#!/usr/bin/env python3
"""Test script to verify browser-use response_format fix"""

import asyncio
import sys
from contextlib import suppress

from app.core.config import get_settings
from app.infrastructure.external.browser.browseruse_browser import BrowserUseService, is_browser_use_available


async def test_browseruse():
    """Test browser-use with a simple task"""

    # Check if browser-use is available
    if not is_browser_use_available():
        return False

    # Get settings
    settings = get_settings()

    # Create browser-use service
    # Note: This is a simplified test - in production, the CDP URL comes from sandbox
    cdp_url = "http://localhost:9222"

    try:
        service = BrowserUseService(
            cdp_url=cdp_url,
            skip_video_urls=True,
            auto_dismiss_dialogs=True,
        )

        # Try to execute a simple autonomous task

        result = await service.execute_autonomous_task(
            task="Go to example.com and tell me the page title",
            max_steps=5,
            start_url="https://example.com",
        )

        if result.get("success"):
            if result.get("final_result"):
                pass

            if result.get("actions"):
                for _action in result["actions"][:3]:
                    pass

            # Check for response_format errors in the result
            result_str = str(result)
            return not ("response_format" in result_str.lower() or "unavailable" in result_str.lower())
        error = result.get("error", "Unknown error")

        # Check if it's the response_format error - return the negated condition
        # Other errors are acceptable for this test (e.g., connection issues)
        return not ("response_format" in error.lower() or "unavailable" in error.lower())

    except Exception as e:
        error_str = str(e)

        # Check if it's the response_format error - return the negated condition
        # Other errors might be infrastructure issues (Chrome not available, etc.)
        return not ("response_format" in error_str.lower() or "unavailable" in error_str.lower())

    finally:
        # Cleanup
        with suppress(Exception):
            if "service" in locals():
                await service.cleanup()


if __name__ == "__main__":
    try:
        success = asyncio.run(test_browseruse())

        if success:
            pass
        else:
            pass

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
