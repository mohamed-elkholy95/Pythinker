#!/usr/bin/env python3
"""Quick validation script to check code structure without running tests."""

import ast
import sys
from pathlib import Path


def validate_file_syntax(file_path: Path) -> tuple[bool, str]:
    """Validate Python file syntax."""
    try:
        with open(file_path, "r") as f:
            code = f.read()
        ast.parse(code)
        return True, "OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_imports(file_path: Path, expected_imports: list[str]) -> tuple[bool, list[str]]:
    """Check if file contains expected imports."""
    try:
        with open(file_path, "r") as f:
            code = f.read()
        tree = ast.parse(code)

        found_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        full_import = f"{node.module}.{alias.name}"
                        found_imports.append(full_import)

        missing = [imp for imp in expected_imports if not any(imp in found for found in found_imports)]
        return len(missing) == 0, missing
    except Exception as e:
        return False, [f"Error: {e}"]


def main():
    """Run validation checks."""
    backend_dir = Path(__file__).parent.parent / "backend"

    print("=" * 60)
    print("Code Structure Validation")
    print("=" * 60)
    print()

    # Files to validate
    files_to_check = [
        "app/core/config.py",
        "app/core/sandbox_pool.py",
        "app/domain/models/pressure.py",
        "app/domain/services/agents/token_manager.py",
        "app/application/services/screenshot_service.py",
        "app/infrastructure/external/browser/playwright_browser.py",
        "app/core/prometheus_metrics.py",
        "app/interfaces/api/rating_routes.py",
        "app/interfaces/dependencies.py",
    ]

    print("Step 1: Syntax Validation")
    print("-" * 60)

    all_valid = True
    for file_path in files_to_check:
        full_path = backend_dir / file_path
        if not full_path.exists():
            print(f"✗ {file_path} - File not found!")
            all_valid = False
            continue

        valid, message = validate_file_syntax(full_path)
        if valid:
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} - {message}")
            all_valid = False

    print()
    print("Step 2: Import Validation")
    print("-" * 60)

    # Check sandbox_pool.py imports
    sandbox_pool = backend_dir / "app/core/sandbox_pool.py"
    expected = [
        "prometheus_metrics.record_sandbox_health_check",
        "prometheus_metrics.record_sandbox_oom_kill",
        "prometheus_metrics.record_sandbox_runtime_crash",
    ]

    valid, missing = check_imports(sandbox_pool, expected)
    if valid:
        print("✓ sandbox_pool.py - All required imports present")
    else:
        print(f"✗ sandbox_pool.py - Missing imports: {missing}")
        all_valid = False

    # Check prometheus_metrics.py has record functions
    metrics_file = backend_dir / "app/core/prometheus_metrics.py"
    with open(metrics_file, "r") as f:
        metrics_content = f.read()

    required_functions = [
        "def record_sandbox_health_check",
        "def record_sandbox_oom_kill",
        "def record_sandbox_runtime_crash",
    ]

    for func in required_functions:
        if func in metrics_content:
            print(f"✓ prometheus_metrics.py - {func} found")
        else:
            print(f"✗ prometheus_metrics.py - {func} not found")
            all_valid = False

    print()
    print("Step 3: New Metrics Validation")
    print("-" * 60)

    required_metrics = [
        "browser_heavy_page_detections_total",
        "browser_wikipedia_summary_mode_total",
        "browser_memory_pressure_total",
        "browser_memory_restarts_total",
        "element_extraction_cache_hits_total",
        "element_extraction_cache_misses_total",
        "screenshot_circuit_state",
        "screenshot_retry_attempts_total",
        "sandbox_health_check_total",
        "sandbox_oom_kills_total",
        "sandbox_runtime_crashes_total",
        "token_pressure_level",
        "rating_unauthorized_attempts_total",
    ]

    for metric in required_metrics:
        if metric in metrics_content:
            print(f"✓ Metric defined: {metric}")
        else:
            print(f"✗ Metric missing: {metric}")
            all_valid = False

    print()
    print("Step 4: Test Files Validation")
    print("-" * 60)

    test_files = [
        "tests/infrastructure/external/browser/test_proactive_heavy_page_detection.py",
        "tests/infrastructure/external/browser/test_wikipedia_optimization.py",
        "tests/infrastructure/external/browser/test_graceful_crash_degradation.py",
        "tests/infrastructure/external/browser/test_memory_pressure.py",
        "tests/application/services/test_screenshot_circuit_breaker.py",
        "tests/application/services/test_screenshot_retry_backoff.py",
        "tests/core/test_sandbox_health_monitoring.py",
        "tests/core/test_sandbox_oom_detection.py",
        "tests/domain/services/agents/test_token_manager_new_thresholds.py",
        "tests/interfaces/api/test_rating_endpoint_security.py",
        "tests/integration/test_wikipedia_end_to_end.py",
        "tests/integration/test_screenshot_pool_exhaustion.py",
        "tests/integration/test_sandbox_oom_e2e.py",
        "tests/integration/test_unauthorized_ratings_e2e.py",
    ]

    for test_file in test_files:
        full_path = backend_dir / test_file
        if full_path.exists():
            valid, message = validate_file_syntax(full_path)
            if valid:
                print(f"✓ {test_file}")
            else:
                print(f"✗ {test_file} - {message}")
                all_valid = False
        else:
            print(f"✗ {test_file} - File not found!")
            all_valid = False

    print()
    print("=" * 60)
    if all_valid:
        print("✓ All validations passed!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run: ./scripts/verify_monitoring_fixes.sh")
        print("  2. Or run tests manually: cd backend && pytest tests/ -v")
        print()
        return 0
    else:
        print("✗ Some validations failed!")
        print("=" * 60)
        print()
        print("Please review the errors above and fix them.")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
