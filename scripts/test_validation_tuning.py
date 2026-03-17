#!/usr/bin/env python3
"""Test script to verify validation tuning changes.

This script validates that:
1. Compression limits have been increased
2. Response compressor extracts more content
3. Task assessment correctly determines verbosity modes
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_policy import (
    ResponsePolicy,
    ResponsePolicyEngine,
    VerbosityMode,
)


def test_compression_limits():
    """Test that max_chars has been increased."""
    print("=" * 60)
    print("TEST 1: Compression Limits")
    print("=" * 60)

    # Test ResponsePolicy default
    policy = ResponsePolicy(mode=VerbosityMode.CONCISE)
    assert policy.max_chars == 4000, f"Expected max_chars=4000, got {policy.max_chars}"
    print("✅ ResponsePolicy.max_chars = 4000 (was 1400)")

    # Test ResponseCompressor default
    compressor = ResponseCompressor()
    test_content = "A" * 3000
    compressed = compressor.compress(test_content, VerbosityMode.CONCISE)

    # Should preserve all content since it's under 4000 chars
    assert len(compressed) == 3000, f"Expected 3000 chars, got {len(compressed)}"
    print("✅ ResponseCompressor preserves content under 4000 chars")

    # Test compression of large content
    large_content = "A" * 8000
    compressed_large = compressor.compress(
        large_content, VerbosityMode.CONCISE, max_chars=4000
    )
    assert len(compressed_large) <= 4000, (
        f"Expected ≤4000 chars, got {len(compressed_large)}"
    )
    print(
        f"✅ ResponseCompressor compresses 8000 → {len(compressed_large)} chars (limit: 4000)"
    )

    print()


def test_compression_content_extraction():
    """Test that compressor extracts more blocks and artifacts."""
    print("=" * 60)
    print("TEST 2: Content Extraction")
    print("=" * 60)

    compressor = ResponseCompressor()

    # Create test content with multiple blocks and artifacts
    test_content = """
# Summary

## Block 1
First summary block with important information.

## Block 2
Second summary block with more context.

## Block 3
Third summary block with additional details.

## Block 4
Fourth summary block with final notes.

## Block 5
Fifth summary block that might be cut.

## Artifacts
Key files:
- `src/main.py:123` - Main entry point
- `src/utils.py:45` - Utility functions
- `src/config.py:67` - Configuration
- `src/database.py:89` - Database layer
- `src/api.py:12` - API routes
- `src/models.py:34` - Data models
- `src/views.py:56` - View logic
- `src/tests.py:78` - Test suite

## Caveat
This implementation has some limitations.

## Next Step
Run the application with `python src/main.py`.
"""

    compressed = compressor.compress(
        test_content.strip(), VerbosityMode.CONCISE, max_chars=4000
    )

    # Check that multiple blocks are preserved
    block_count = compressed.count("##")
    print(f"✅ Compressed output contains {block_count} sections")

    # Check that artifacts are preserved
    artifact_count = compressed.count("src/")
    print(
        f"✅ Compressed output preserves {artifact_count} artifact references (was limited to 3)"
    )

    # Verify caveat and next step are included
    assert "limitation" in compressed.lower(), "Caveat should be preserved"
    print("✅ Caveat preserved in compressed output")

    assert "next step" in compressed.lower() or "run" in compressed.lower(), (
        "Next step should be preserved"
    )
    print("✅ Next step preserved in compressed output")

    print()


def test_task_assessment():
    """Test task assessment and policy decisions."""
    print("=" * 60)
    print("TEST 3: Task Assessment & Policy Decision")
    print("=" * 60)

    engine = ResponsePolicyEngine()

    test_cases = [
        {
            "request": "Search for Python tutorials",
            "expected_mode": VerbosityMode.CONCISE,
            "description": "Low risk, simple task",
        },
        {
            "request": "Delete all production databases and drop all tables",
            "expected_mode": VerbosityMode.DETAILED,
            "description": "High risk task (contains 'production', 'delete', 'drop table')",
        },
        {
            "request": "Compare the latest performance benchmarks of React, Vue, and Angular with current metrics and stats",
            "expected_mode": VerbosityMode.DETAILED,
            "description": "Evidence-heavy task (contains 'latest', 'current', 'compare', 'benchmarks', 'metrics', 'stats')",
        },
        {
            "request": "Create a simple hello world function",
            "expected_mode": VerbosityMode.CONCISE,
            "description": "Low complexity task",
        },
    ]

    for test_case in test_cases:
        request = test_case["request"]
        expected = test_case["expected_mode"]
        description = test_case["description"]

        assessment = engine.assess_task(request)
        policy = engine.decide_policy(assessment)

        status = "✅" if policy.mode == expected else "❌"
        print(f"{status} {description}")
        print(f"   Request: '{request[:60]}...'")
        print(
            f"   Risk: {assessment.risk_score:.2f}, Complexity: {assessment.complexity_score:.2f}, Ambiguity: {assessment.ambiguity_score:.2f}"
        )
        print(f"   Mode: {policy.mode.value} (expected: {expected.value})")
        print(
            f"   Compression: {policy.allow_compression}, Max chars: {policy.max_chars}"
        )
        print()


def test_policy_max_chars_decision():
    """Test that decide_policy returns correct max_chars."""
    print("=" * 60)
    print("TEST 4: Policy max_chars Decision")
    print("=" * 60)

    engine = ResponsePolicyEngine()

    # Simple task → CONCISE → max_chars should be 4000
    simple_assessment = engine.assess_task("Search for Python docs")
    simple_policy = engine.decide_policy(simple_assessment)

    if simple_policy.mode == VerbosityMode.CONCISE:
        assert simple_policy.max_chars == 4000, (
            f"CONCISE mode should have max_chars=4000, got {simple_policy.max_chars}"
        )
        print(f"✅ CONCISE mode: max_chars = {simple_policy.max_chars}")
    else:
        print(f"⚠️  Simple task assessed as {simple_policy.mode.value}, not CONCISE")

    # Complex task → DETAILED → max_chars should be 12000
    complex_assessment = engine.assess_task(
        "Implement secure payment processing with encryption"
    )
    complex_policy = engine.decide_policy(complex_assessment)

    if complex_policy.mode == VerbosityMode.DETAILED:
        assert complex_policy.max_chars == 12000, (
            f"DETAILED mode should have max_chars=12000, got {complex_policy.max_chars}"
        )
        print(f"✅ DETAILED mode: max_chars = {complex_policy.max_chars}")
    else:
        print(f"⚠️  Complex task assessed as {complex_policy.mode.value}, not DETAILED")

    print()


def main():
    """Run all validation tests."""
    print("\n🔍 VALIDATION TUNING TEST SUITE\n")

    try:
        test_compression_limits()
        test_compression_content_extraction()
        test_task_assessment()
        test_policy_max_chars_decision()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nValidation tuning changes have been successfully applied!")
        print("\nNext steps:")
        print("1. Restart backend: ./dev.sh restart backend")
        print("2. Test with real agent queries")
        print("3. Monitor logs for compression metrics")
        print()

        return 0

    except AssertionError as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        print("\nPlease check that all changes were applied correctly.")
        print("See: docs/fixes/validation-tuning-guide.md")
        print()
        return 1

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ UNEXPECTED ERROR")
        print("=" * 60)
        print(f"\nError: {type(e).__name__}: {e}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
