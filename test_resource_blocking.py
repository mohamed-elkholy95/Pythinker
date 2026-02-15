#!/usr/bin/env python3
"""Test script to verify browser resource blocking settings."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.core.config import get_settings
from app.infrastructure.external.browser.playwright_browser import BLOCKABLE_RESOURCE_TYPES


async def test_settings():
    """Test that settings are loaded correctly."""
    settings = get_settings()

    print("=" * 60)
    print("Browser Resource Blocking Configuration Test")
    print("=" * 60)
    print()

    print("✓ Settings loaded successfully!")
    print()
    print(f"1. Default blocking enabled: {settings.browser_block_resources_default}")
    print(f"   → Expected: False (disabled by default)")
    print()

    print(f"2. Blocked resource types: {settings.browser_blocked_resource_types}")
    print(f"   → Expected: 'image,media' (only heavy resources)")
    print()

    print(f"3. Parsed as set: {settings.browser_blocked_types_set}")
    print(f"   → Expected: {{'image', 'media'}}")
    print()

    print(f"4. All blockable types: {BLOCKABLE_RESOURCE_TYPES}")
    print(f"   → These CAN be blocked: image, media, font, stylesheet")
    print()

    # Verify the configuration
    issues = []

    if settings.browser_block_resources_default:
        issues.append("⚠️  WARNING: Resource blocking is ENABLED by default")
        issues.append("   This will block resources on all pages unless explicitly disabled")

    if "stylesheet" in settings.browser_blocked_types_set:
        issues.append("⚠️  WARNING: Stylesheets are being blocked!")
        issues.append("   Pages will appear unstyled (like GitHub)")

    if "font" in settings.browser_blocked_types_set:
        issues.append("⚠️  WARNING: Fonts are being blocked!")
        issues.append("   Pages will have missing or fallback fonts")

    print("-" * 60)
    if issues:
        print("CONFIGURATION ISSUES DETECTED:")
        print()
        for issue in issues:
            print(issue)
        print()
        print("Fix: Update .env with:")
        print("  BROWSER_BLOCK_RESOURCES_DEFAULT=false")
        print("  BROWSER_BLOCKED_RESOURCE_TYPES=image,media")
        return False
    else:
        print("✅ CONFIGURATION LOOKS GOOD!")
        print()
        print("Current behavior:")
        print("  - Resource blocking: DISABLED by default")
        print("  - Only blocks: images, media (when enabled)")
        print("  - Allows: CSS, fonts (critical for page rendering)")
        print("  - Always blocks: ads, trackers (regardless of settings)")
        return True


if __name__ == "__main__":
    result = asyncio.run(test_settings())
    sys.exit(0 if result else 1)
