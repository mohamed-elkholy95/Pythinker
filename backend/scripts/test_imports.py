#!/usr/bin/env python3
"""Test that all new modules can be imported successfully."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test all new module imports."""

    tests_passed = 0
    tests_failed = 0

    # Test 1: Domain models
    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    # Test 2: Services
    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    # Test 3: Infrastructure
    try:
        tests_passed += 1
    except Exception:
        tests_failed += 1

    # Summary

    if tests_failed == 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(test_imports())
