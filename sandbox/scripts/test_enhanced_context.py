#!/usr/bin/env python3
"""
Test script for enhanced sandbox context generation

Tests the new command reference enhancements including:
- Bash command examples
- Python stdlib modules
- Node.js built-in modules
- Execution patterns
- Environment variables
- Resource limits
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.generate_sandbox_context import EnvironmentScanner


def test_bash_commands():
    """Test bash command scanning"""
    print("Testing bash command scanning...")
    scanner = EnvironmentScanner()
    bash_commands = scanner.scan_bash_commands()

    assert "file_operations" in bash_commands
    assert "text_processing" in bash_commands
    assert "network" in bash_commands

    # Check for specific commands
    assert "grep" in bash_commands["file_operations"]
    assert "jq" in bash_commands["text_processing"]
    assert "curl" in bash_commands["network"]

    # Check examples exist
    assert len(bash_commands["file_operations"]["grep"]["examples"]) > 0
    print(f"✓ Bash commands: {len(bash_commands)} categories")


def test_python_stdlib():
    """Test Python stdlib scanning"""
    print("Testing Python stdlib scanning...")
    scanner = EnvironmentScanner()
    stdlib = scanner.scan_python_stdlib()

    assert "by_category" in stdlib
    assert "total_count" in stdlib
    assert stdlib["total_count"] > 0

    # Check key categories
    categories = stdlib["by_category"]
    assert "core" in categories
    assert "file_io" in categories

    # Verify common modules are detected
    core_modules = categories.get("core", [])
    assert "os" in core_modules
    assert "sys" in core_modules
    assert "json" in core_modules

    print(
        f"✓ Python stdlib: {stdlib['total_count']} modules in {len(categories)} categories"
    )


def test_nodejs_builtins():
    """Test Node.js built-in modules scanning"""
    print("Testing Node.js built-ins scanning...")
    scanner = EnvironmentScanner()
    builtins = scanner.scan_nodejs_builtins()

    assert "by_category" in builtins
    assert "total_count" in builtins
    assert builtins["total_count"] > 0

    # Check key categories
    categories = builtins["by_category"]
    assert "core" in categories
    assert "file_system" in categories

    # Verify common modules are listed
    core_modules = categories.get("core", [])
    assert "fs" in core_modules
    assert "http" in core_modules
    assert "path" in core_modules

    print(
        f"✓ Node.js builtins: {builtins['total_count']} modules in {len(categories)} categories"
    )


def test_environment_variables():
    """Test environment variables scanning"""
    print("Testing environment variables scanning...")
    scanner = EnvironmentScanner()
    env_vars = scanner.scan_environment_variables()

    # Should have at least some common vars
    assert len(env_vars) > 0

    # Common variables that should exist
    assert "PATH" in env_vars
    assert "HOME" in env_vars

    print(f"✓ Environment variables: {len(env_vars)} vars found")


def test_execution_patterns():
    """Test execution patterns"""
    print("Testing execution patterns...")
    scanner = EnvironmentScanner()
    patterns = scanner.scan_execution_patterns()

    assert "python" in patterns
    assert "nodejs" in patterns
    assert "shell" in patterns

    # Check specific patterns
    assert "run_script" in patterns["python"]
    assert "pip_install" in patterns["python"]
    assert "run_script" in patterns["nodejs"]
    assert "npm_install" in patterns["nodejs"]

    print(f"✓ Execution patterns: {len(patterns)} languages")


def test_resource_limits():
    """Test resource limits scanning"""
    print("Testing resource limits scanning...")
    scanner = EnvironmentScanner()
    limits = scanner.scan_resource_limits()

    # Should have at least shared_memory
    assert "shared_memory" in limits

    print(f"✓ Resource limits: {len(limits)} metrics")


def test_full_context_generation():
    """Test complete context generation with new fields"""
    print("\nTesting full context generation...")
    scanner = EnvironmentScanner()
    context = scanner.scan_all()

    # Verify new fields are present
    env = context["environment"]

    assert "bash_commands" in env
    assert "python_stdlib" in env
    assert "nodejs_builtins" in env
    assert "environment_variables" in env
    assert "execution_patterns" in env
    assert "resource_limits" in env

    # Verify existing fields still work
    assert "os" in env
    assert "python" in env
    assert "nodejs" in env

    print("✓ Full context generation includes all enhanced fields")

    # Print summary
    print("\n=== Context Summary ===")
    print(f"OS: {env['os'].get('distribution')}")
    print(f"Python packages: {env['python'].get('package_count')}")
    print(f"Python stdlib modules: {env['python_stdlib'].get('total_count')}")
    print(f"Node.js builtins: {env['nodejs_builtins'].get('total_count')}")
    print(f"Bash command categories: {len(env['bash_commands'])}")
    print(f"Environment variables: {len(env['environment_variables'])}")
    print(f"Execution pattern languages: {len(env['execution_patterns'])}")
    print(f"Checksum: {context.get('checksum')}")


def test_json_serialization():
    """Test that enhanced context can be serialized to JSON"""
    print("\nTesting JSON serialization...")
    scanner = EnvironmentScanner()
    context = scanner.scan_all()

    # Try to serialize
    try:
        json_str = json.dumps(context, indent=2)
        assert len(json_str) > 1000  # Should be substantial
        print(f"✓ JSON serialization: {len(json_str)} bytes")

        # Verify it can be parsed back
        parsed = json.loads(json_str)
        assert "environment" in parsed
        print("✓ JSON deserialization successful")

    except Exception as e:
        print(f"✗ JSON serialization failed: {e}")
        raise


def test_markdown_generation():
    """Test markdown generation with new sections"""
    print("\nTesting markdown generation...")
    scanner = EnvironmentScanner()
    scanner.scan_all()
    markdown = scanner.generate_markdown()

    # Check for new sections in markdown
    assert "Execution Patterns" in markdown
    assert "Python Standard Library" in markdown
    assert "Node.js Built-in Modules" in markdown
    assert "Bash Command Examples" in markdown
    assert "Environment Variables" in markdown

    print(f"✓ Markdown generation: {len(markdown)} characters")
    print("✓ All new sections present in markdown")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Enhanced Sandbox Context Generation Tests")
    print("=" * 60)
    print()

    tests = [
        test_bash_commands,
        test_python_stdlib,
        test_nodejs_builtins,
        test_environment_variables,
        test_execution_patterns,
        test_resource_limits,
        test_full_context_generation,
        test_json_serialization,
        test_markdown_generation,
    ]

    failed = []

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed.append(test.__name__)
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print(f"SUCCESS: All {len(tests)} tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
