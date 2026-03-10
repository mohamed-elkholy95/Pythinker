from __future__ import annotations

import subprocess
import sys


def test_requests_import_emits_no_dependency_warning() -> None:
    """Fail fast when the environment drifts into a requests-incompatible state."""
    check_script = """
import json
import warnings

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    import requests  # noqa: F401

dependency_warnings = [
    {
        "category": warning.category.__name__,
        "message": str(warning.message),
    }
    for warning in caught
    if warning.category.__name__ == "RequestsDependencyWarning"
]

if dependency_warnings:
    print(json.dumps(dependency_warnings))
    raise SystemExit(1)
"""
    # Safe in-test subprocess: both the interpreter and inline script are fixed inputs.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", check_script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "Importing requests emitted RequestsDependencyWarning. "
        "Reinstall the backend dependencies so the declared compatibility "
        f"constraints are enforced.\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
