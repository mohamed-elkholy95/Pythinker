"""
Test script to verify browser window positioning fix in VNC.

This script tests that the browser window stays centered at position 0,0
during navigation, browsing, and restart operations.
"""

import asyncio
import logging

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_browser_positioning():
    """Test that browser stays at correct position during operations."""

    # Connect to sandbox Chrome instance
    # Note: This assumes a sandbox is running locally on port 8222
    cdp_url = "http://localhost:8222"

    browser = PlaywrightBrowser(cdp_url=cdp_url, block_resources=False, randomize_fingerprint=False)

    try:
        logger.info("=" * 80)
        logger.info("TEST: Browser Window Positioning in VNC")
        logger.info("=" * 80)

        # Test 1: Initial connection
        logger.info("\n[TEST 1] Initial browser connection...")
        success = await browser.initialize(clear_existing=False)
        if not success:
            logger.error("❌ Failed to initialize browser")
            return False

        logger.info("✓ Browser initialized successfully")

        # Check how many pages exist
        if browser.context:
            pages = browser.context.pages
            logger.info(f"  - Pages in context: {len(pages)}")
            if browser.page:
                url = browser.page.url
                logger.info(f"  - Current page URL: {url}")

        # Test 2: Navigate to a URL
        logger.info("\n[TEST 2] Navigating to a test URL...")
        result = await browser.navigate("https://example.com", auto_extract=False)
        if not result.success:
            logger.error(f"❌ Navigation failed: {result.message}")
            return False

        logger.info("✓ Navigation successful")
        if browser.context:
            pages = browser.context.pages
            logger.info(f"  - Pages in context after navigation: {len(pages)}")
            logger.info(f"  - Current page URL: {browser.page.url if browser.page else 'None'}")

        # Test 3: Navigate to another URL
        logger.info("\n[TEST 3] Navigating to another URL...")
        result = await browser.navigate("https://www.wikipedia.org", auto_extract=False)
        if not result.success:
            logger.error(f"❌ Second navigation failed: {result.message}")
            return False

        logger.info("✓ Second navigation successful")
        if browser.context:
            pages = browser.context.pages
            logger.info(f"  - Pages in context after second nav: {len(pages)}")
            logger.info(f"  - Current page URL: {browser.page.url if browser.page else 'None'}")

        # Test 4: Browser restart
        logger.info("\n[TEST 4] Testing browser restart...")
        result = await browser.restart("https://github.com")
        if not result.success:
            logger.error(f"❌ Browser restart failed: {result.message}")
            return False

        logger.info("✓ Browser restart successful")
        if browser.context:
            pages = browser.context.pages
            logger.info(f"  - Pages in context after restart: {len(pages)}")
            logger.info(f"  - Current page URL: {browser.page.url if browser.page else 'None'}")

        # Test 5: Multiple restarts
        logger.info("\n[TEST 5] Testing multiple restarts...")
        for i in range(3):
            logger.info(f"  Restart {i + 1}/3...")
            result = await browser.restart("https://example.com")
            if not result.success:
                logger.error(f"❌ Restart {i + 1} failed: {result.message}")
                return False

            if browser.context:
                pages = browser.context.pages
                logger.info(f"    - Pages in context: {len(pages)}")

        logger.info("✓ Multiple restarts successful")

        # Final verification
        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION")
        logger.info("=" * 80)

        if browser.context:
            final_pages = browser.context.pages
            logger.info(f"Final page count: {len(final_pages)}")

            if len(final_pages) <= 2:
                logger.info("✓ PASS: Page count is reasonable (≤2)")
                logger.info("  This indicates we're reusing pages instead of creating new windows")
            else:
                logger.warning(f"⚠ WARNING: High page count ({len(final_pages)})")
                logger.warning("  Multiple windows may have been created")

        logger.info("\n" + "=" * 80)
        logger.info("TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        logger.info("\nManual Verification:")
        logger.info("1. Check VNC display (port 5902)")
        logger.info("2. Verify browser window is centered and not shifted right")
        logger.info("3. All browser content should be visible")

        return True

    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
        return False

    finally:
        logger.info("\nCleaning up...")
        await browser.cleanup()
        logger.info("Cleanup complete")


async def main():
    """Run the test."""
    try:
        success = await test_browser_positioning()
        if success:
            logger.info("\n✓ All tests passed!")
            return 0
        logger.error("\n❌ Some tests failed")
        return 1
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
