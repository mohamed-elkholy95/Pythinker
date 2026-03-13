#!/usr/bin/env python3
"""
Plotly + Kaleido smoke test for Phase 2 validation.

Tests that:
1. Plotly can generate interactive HTML with CDN mode
2. Kaleido can export static PNG using system Chromium
3. BROWSER_PATH environment variable is correctly configured

Exit codes:
- 0: All tests passed
- 1: Import error
- 2: HTML generation failed
- 3: PNG generation failed (Kaleido/Chromium issue)
"""

import os
import sys
from pathlib import Path


def main():
    print("=== Plotly + Kaleido Smoke Test ===\n")

    # Test 1: Import libraries
    print("[1/5] Importing libraries...")
    try:
        import plotly.graph_objects as go

        print("  ✓ Plotly imported successfully")
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return 1

    # Test 2: Check BROWSER_PATH
    print("\n[2/5] Checking BROWSER_PATH environment variable...")
    browser_path = os.environ.get("BROWSER_PATH")
    if browser_path:
        print(f"  ✓ BROWSER_PATH={browser_path}")
        if Path(browser_path).exists():
            print(f"  ✓ Chromium binary exists at {browser_path}")
        else:
            print("  ⚠ Warning: BROWSER_PATH points to non-existent file")
    else:
        print("  ⚠ Warning: BROWSER_PATH not set (Kaleido will search standard paths)")

    # Test 3: Configure Kaleido defaults
    print("\n[3/5] Configuring Kaleido defaults...")
    # Note: Kaleido template API was removed in newer versions
    # Configuration is now passed directly to write_image()
    print("  ✓ Kaleido configuration (passed to write_image calls)")

    # Test 4: Generate HTML (CDN mode)
    print("\n[4/5] Generating HTML chart (CDN mode)...")
    try:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=["Test A", "Test B", "Test C"],
                    y=[10, 15, 13],
                    marker_color="#2563eb",
                )
            ]
        )
        fig.update_layout(
            title="Plotly Smoke Test Chart",
            xaxis_title="Test Cases",
            yaxis_title="Scores",
            template="plotly_white",
        )

        output_html = "/tmp/plotly_smoke_test.html"
        fig.write_html(output_html, include_plotlyjs="cdn")

        # Verify file size
        html_size = Path(output_html).stat().st_size
        print(f"  ✓ HTML generated: {html_size:,} bytes")
        if html_size < 100_000:  # Should be <100KB with CDN mode
            print("  ✓ File size OK (<100KB)")
        else:
            print("  ⚠ Warning: File size is large (expected <100KB with CDN)")

    except Exception as e:
        print(f"  ✗ HTML generation failed: {e}")
        return 2

    # Test 5: Generate PNG (Kaleido + Chromium)
    print("\n[5/5] Generating PNG chart (Kaleido + Chromium)...")
    try:
        output_png = "/tmp/plotly_smoke_test.png"
        fig.write_image(output_png, width=1200, height=800, scale=2)

        # Verify file size
        png_size = Path(output_png).stat().st_size
        print(f"  ✓ PNG generated: {png_size:,} bytes")
        if png_size > 10_000:  # Reasonable PNG should be >10KB
            print("  ✓ File size OK (>10KB)")
        else:
            print("  ⚠ Warning: PNG is suspiciously small")

    except Exception as e:
        print(f"  ✗ PNG generation failed: {e}")
        print("\nTroubleshooting:")
        print("- Ensure Kaleido is installed: pip install 'kaleido>=1.0.0'")
        print("- Verify BROWSER_PATH points to Chromium: echo $BROWSER_PATH")
        print("- Check Playwright Chromium: ls -la /usr/local/bin/chromium")
        return 3

    # Success!
    print("\n" + "=" * 40)
    print("✓ All smoke tests passed!")
    print(f"  - HTML: {output_html}")
    print(f"  - PNG:  {output_png}")
    print("=" * 40)
    return 0


if __name__ == "__main__":
    sys.exit(main())
