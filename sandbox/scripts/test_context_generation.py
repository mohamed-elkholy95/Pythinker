#!/usr/bin/env python3
"""
Test script for sandbox context generation

Validates that the context system works correctly and generates expected output.

Usage:
    python3 test_context_generation.py
"""

import sys
import json
from pathlib import Path
from generate_sandbox_context import EnvironmentScanner


def test_scanner_initialization():
    """Test scanner can be initialized"""
    print("Testing scanner initialization...", end=" ")
    scanner = EnvironmentScanner("/tmp/test_context.json")
    assert scanner.output_path == "/tmp/test_context.json"
    assert scanner.context["version"] == "1.0.0"
    print("✓")


def test_os_scanning():
    """Test OS info scanning"""
    print("Testing OS scanning...", end=" ")
    scanner = EnvironmentScanner()
    os_info = scanner.scan_os_info()

    assert "distribution" in os_info
    assert "kernel" in os_info
    assert "user" in os_info
    assert os_info["user"] in ["ubuntu", "root"]  # Depends on runtime context
    print("✓")


def test_python_scanning():
    """Test Python environment scanning"""
    print("Testing Python scanning...", end=" ")
    scanner = EnvironmentScanner()
    python_info = scanner.scan_python_environment()

    assert "version" in python_info
    assert "Python" in python_info["version"]
    assert "pip_version" in python_info
    print("✓")


def test_nodejs_scanning():
    """Test Node.js environment scanning"""
    print("Testing Node.js scanning...", end=" ")
    scanner = EnvironmentScanner()
    node_info = scanner.scan_nodejs_environment()

    assert "version" in node_info
    # May not be installed in all environments
    if node_info["version"]:
        assert "v" in node_info["version"]
    print("✓")


def test_tools_scanning():
    """Test system tools scanning"""
    print("Testing tools scanning...", end=" ")
    scanner = EnvironmentScanner()
    tools = scanner.scan_system_tools()

    assert "development" in tools
    assert "text_processing" in tools
    # Git should be available
    if "git" in tools["development"]:
        assert tools["development"]["git"]["available"]
    print("✓")


def test_full_scan():
    """Test complete environment scan"""
    print("Testing full environment scan...", end=" ")
    scanner = EnvironmentScanner()
    context = scanner.scan_all()

    assert "environment" in context
    assert "os" in context["environment"]
    assert "python" in context["environment"]
    assert "checksum" in context
    assert len(context["checksum"]) > 0
    print("✓")


def test_json_output():
    """Test JSON file generation"""
    print("Testing JSON output...", end=" ")
    output_path = "/tmp/test_sandbox_context.json"
    scanner = EnvironmentScanner(output_path)
    scanner.scan_all()
    scanner.save_json()

    # Verify file exists
    assert Path(output_path).exists()

    # Verify valid JSON
    with open(output_path, "r") as f:
        data = json.load(f)

    assert "environment" in data
    assert "version" in data
    print("✓")


def test_markdown_output():
    """Test Markdown file generation"""
    print("Testing Markdown output...", end=" ")
    output_md = "/tmp/test_sandbox_context.md"
    scanner = EnvironmentScanner()
    scanner.scan_all()
    scanner.save_markdown(output_md)

    # Verify file exists
    assert Path(output_md).exists()

    # Verify contains expected sections
    with open(output_md, "r") as f:
        content = f.read()

    assert "# Sandbox Environment Context" in content
    assert "## Python Environment" in content
    assert "## System Tools" in content
    print("✓")


def test_checksum_generation():
    """Test checksum changes with environment"""
    print("Testing checksum generation...", end=" ")
    scanner1 = EnvironmentScanner()
    checksum1 = scanner1.generate_checksum()

    scanner2 = EnvironmentScanner()
    checksum2 = scanner2.generate_checksum()

    # Same day should have same checksum
    assert checksum1 == checksum2
    assert len(checksum1) == 16  # Should be 16 chars
    print("✓")


def validate_structure(context: dict):
    """Validate context structure completeness"""
    print("Validating context structure...", end=" ")

    required_top_level = ["generated_at", "version", "environment", "checksum"]
    for key in required_top_level:
        assert key in context, f"Missing top-level key: {key}"

    env = context["environment"]
    required_env_sections = [
        "os",
        "python",
        "nodejs",
        "system_tools",
        "capabilities",
        "directories",
    ]
    for key in required_env_sections:
        assert key in env, f"Missing environment section: {key}"

    # Validate OS section
    assert "distribution" in env["os"]
    assert "user" in env["os"]

    # Validate Python section
    assert "version" in env["python"]
    assert "package_count" in env["python"]

    print("✓")


def benchmark_scan_performance():
    """Benchmark scanning performance"""
    print("Benchmarking scan performance...", end=" ")
    import time

    scanner = EnvironmentScanner()

    start = time.time()
    scanner.scan_all()
    duration = time.time() - start

    assert duration < 30, f"Scan took too long: {duration:.2f}s"
    print(f"✓ ({duration:.2f}s)")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Sandbox Context Generation Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_scanner_initialization,
        test_os_scanning,
        test_python_scanning,
        test_nodejs_scanning,
        test_tools_scanning,
        test_full_scan,
        test_json_output,
        test_markdown_output,
        test_checksum_generation,
        benchmark_scan_performance,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    # Validate a complete scan
    if failed == 0:
        print("\nRunning final validation...")
        scanner = EnvironmentScanner()
        context = scanner.scan_all()
        validate_structure(context)
        print("\n✓ All tests passed! Context system is working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
