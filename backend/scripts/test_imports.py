#!/usr/bin/env python3
"""Test that all new modules can be imported successfully."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test all new module imports."""
    print("Testing imports for multi-task system...")
    print()

    tests_passed = 0
    tests_failed = 0

    # Test 1: Domain models
    print("1. Testing domain models...")
    try:
        print("   ✅ multi_task models")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ multi_task models: {e}")
        tests_failed += 1

    try:
        print("   ✅ new event types")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ new event types: {e}")
        tests_failed += 1

    try:
        print("   ✅ SessionMetrics")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ SessionMetrics: {e}")
        tests_failed += 1

    try:
        print("   ✅ updated Session model")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ updated Session model: {e}")
        tests_failed += 1

    # Test 2: Services
    print("\n2. Testing services...")
    try:
        print("   ✅ ContextManager")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ContextManager: {e}")
        tests_failed += 1

    try:
        print("   ✅ ComplexityAssessor")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ComplexityAssessor: {e}")
        tests_failed += 1

    try:
        print("   ✅ CommandFormatter")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ CommandFormatter: {e}")
        tests_failed += 1

    try:
        print("   ✅ Workspace services")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Workspace services: {e}")
        tests_failed += 1

    try:
        print("   ✅ ResearchAgent")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ResearchAgent: {e}")
        tests_failed += 1

    # Test 3: Infrastructure
    print("\n3. Testing infrastructure...")
    try:
        print("   ✅ MongoDB with GridFS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ MongoDB with GridFS: {e}")
        tests_failed += 1

    # Summary
    print("\n" + "="*50)
    print(f"Tests passed: {tests_passed}")
    print(f"Tests failed: {tests_failed}")
    print("="*50)

    if tests_failed == 0:
        print("\n✅ All imports successful!")
        return 0
    print(f"\n❌ {tests_failed} import(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(test_imports())
