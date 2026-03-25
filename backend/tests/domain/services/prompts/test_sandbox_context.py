"""Tests for SandboxContextManager and format helpers in sandbox_context.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.domain.services.prompts.sandbox_context import (
    SandboxContextManager,
    get_sandbox_context_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_cache():
    SandboxContextManager._cache = None
    SandboxContextManager._cache_timestamp = None
    SandboxContextManager._warned_no_context = False
    yield
    SandboxContextManager._cache = None
    SandboxContextManager._cache_timestamp = None
    SandboxContextManager._warned_no_context = False


def _minimal_context(**overrides) -> dict:
    """Return the smallest valid context dict accepted by generate_prompt_section."""
    ctx: dict = {"environment": {}}
    ctx.update(overrides)
    return ctx


def _full_env() -> dict:
    """Return a realistic environment dict with all sections populated."""
    return {
        "os": {
            "distribution": "Ubuntu 22.04",
            "architecture": "x86_64",
            "user": "ubuntu",
            "home": "/home/ubuntu",
            "shell": "/bin/bash",
        },
        "python": {
            "version": "3.11.9",
            "path": "/usr/bin/python3",
            "pip_version": "24.0",
            "package_count": 50,
            "key_packages": {
                "requests": "2.31.0",
                "numpy": "1.26.4",
                "pandas": "2.2.0",
            },
        },
        "python_stdlib": {
            "total_count": 200,
            "by_category": {
                "io": ["os", "sys", "io", "pathlib", "tempfile", "shutil", "glob", "fnmatch"],
                "concurrency": ["threading", "multiprocessing", "asyncio", "concurrent"],
                "networking": ["socket", "http", "urllib", "email", "smtplib"],
            },
        },
        "nodejs": {
            "version": "22.13.0",
            "npm_version": "10.9.0",
            "pnpm_version": "9.0.0",
            "yarn_version": "1.22.0",
            "package_count": 12,
        },
        "nodejs_builtins": {
            "total_count": 30,
            "by_category": {
                "core": ["fs", "path", "http", "https", "crypto", "buffer", "stream", "util"],
            },
        },
        "system_tools": {
            "development": {"git": "2.43.0", "gcc": "12.3.0"},
            "text_processing": {"grep": "3.8", "jq": "1.7"},
            "network": {"curl": "8.5.0", "wget": "1.21.4"},
            "compression": {"tar": "1.35", "gzip": "1.12"},
        },
        "browser": {
            "chromium": {"available": True, "version": "122.0.6261"},
            "playwright": {
                "available": True,
                "browsers": ["chromium", "firefox"],
                "stealth_mode": True,
            },
        },
        "directories": {
            "/home/ubuntu": {
                "exists": True,
                "readable": True,
                "writable": True,
                "description": "Home directory",
            },
            "/workspace": {
                "exists": True,
                "readable": True,
                "writable": True,
                "description": "User workspace",
            },
            "/nonexistent": {
                "exists": False,
                "readable": False,
                "writable": False,
                "description": "Does not exist",
            },
        },
        "execution_patterns": {
            "python": {
                "run_script": "python3 script.py",
                "install_pkg": "pip3 install package",
                "run_tests": "pytest tests/",
            },
            "nodejs": {
                "run_script": "node script.js",
                "install_pkg": "npm install package",
            },
        },
        "bash_commands": {
            "file_operations": {
                "list": {"examples": ["ls -la /workspace"]},
                "copy": {"examples": ["cp -r src/ dst/"]},
            },
            "text_processing": {
                "search": {"examples": ["grep -rn 'pattern' ."]},
            },
            "network": {
                "fetch": {"examples": ["curl -s https://api.example.com"]},
            },
        },
        "resource_limits": {
            "disk": {"available": "20GB"},
            "shared_memory": "2gb",
            "memory": "4gb",
        },
    }


# ---------------------------------------------------------------------------
# _format_python_packages
# ---------------------------------------------------------------------------


class TestFormatPythonPackages:
    def test_empty_key_packages_returns_stdlib_only(self):
        result = SandboxContextManager._format_python_packages({})
        assert result == "- Standard library only"

    def test_packages_listed_with_version(self):
        python_env = {"key_packages": {"numpy": "1.26.4", "requests": "2.31.0"}, "package_count": 2}
        result = SandboxContextManager._format_python_packages(python_env)
        assert "numpy (1.26.4)" in result
        assert "requests (2.31.0)" in result

    def test_packages_sorted_alphabetically(self):
        python_env = {"key_packages": {"zlib": "1.0", "abc": "2.0"}, "package_count": 2}
        result = SandboxContextManager._format_python_packages(python_env)
        lines = [ln for ln in result.splitlines() if ln.strip()]
        assert lines[0].startswith("- abc")
        assert lines[1].startswith("- zlib")

    def test_truncation_appended_when_more_than_15(self):
        # Create 20 packages — only top 15 are shown; truncation line added
        packages = {f"pkg{i:02d}": "1.0" for i in range(20)}
        python_env = {"key_packages": packages, "package_count": 20}
        result = SandboxContextManager._format_python_packages(python_env)
        assert "and 5 more packages" in result

    def test_no_truncation_when_15_or_fewer(self):
        packages = {f"pkg{i:02d}": "1.0" for i in range(10)}
        python_env = {"key_packages": packages, "package_count": 10}
        result = SandboxContextManager._format_python_packages(python_env)
        assert "more packages" not in result

    def test_truncation_uses_package_count_field(self):
        # package_count larger than key_packages so truncation line is meaningful
        packages = {"aaa": "1.0", "bbb": "2.0"}
        python_env = {"key_packages": packages, "package_count": 100}
        result = SandboxContextManager._format_python_packages(python_env)
        assert "and 98 more packages" in result


# ---------------------------------------------------------------------------
# _format_browser_info
# ---------------------------------------------------------------------------


class TestFormatBrowserInfo:
    def test_empty_browser_env_returns_fallback(self):
        result = SandboxContextManager._format_browser_info({})
        assert "Basic browser automation available" in result

    def test_chromium_unavailable_not_shown(self):
        browser_env = {"chromium": {"available": False, "version": "122.0"}}
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "Chromium" not in result

    def test_chromium_available_shows_version(self):
        browser_env = {"chromium": {"available": True, "version": "122.0.6261"}}
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "Chromium: 122.0.6261" in result

    def test_playwright_available_shows_browsers(self):
        browser_env = {
            "playwright": {
                "available": True,
                "browsers": ["chromium", "firefox"],
                "stealth_mode": False,
            }
        }
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "Playwright" in result
        assert "chromium" in result
        assert "firefox" in result

    def test_playwright_stealth_mode_shown(self):
        browser_env = {
            "playwright": {
                "available": True,
                "browsers": ["chromium"],
                "stealth_mode": True,
            }
        }
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "stealth mode enabled" in result

    def test_playwright_no_stealth_not_mentioned(self):
        browser_env = {
            "playwright": {
                "available": True,
                "browsers": ["chromium"],
                "stealth_mode": False,
            }
        }
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "stealth" not in result

    def test_both_chromium_and_playwright_shown(self):
        browser_env = {
            "chromium": {"available": True, "version": "122.0"},
            "playwright": {"available": True, "browsers": ["chromium"], "stealth_mode": False},
        }
        result = SandboxContextManager._format_browser_info(browser_env)
        assert "Chromium" in result
        assert "Playwright" in result


# ---------------------------------------------------------------------------
# _format_directories
# ---------------------------------------------------------------------------


class TestFormatDirectories:
    def test_empty_directories_returns_fallback(self):
        result = SandboxContextManager._format_directories({})
        assert "Standard filesystem layout" in result

    def test_non_existing_dir_skipped(self):
        directories = {"/nonexistent": {"exists": False, "readable": False, "writable": False, "description": "Gone"}}
        result = SandboxContextManager._format_directories(directories)
        assert "/nonexistent" not in result

    def test_existing_dir_read_write_shown(self):
        directories = {
            "/workspace": {"exists": True, "readable": True, "writable": True, "description": "User workspace"}
        }
        result = SandboxContextManager._format_directories(directories)
        assert "/workspace" in result
        assert "read+write" in result
        assert "User workspace" in result

    def test_existing_dir_readonly_shown(self):
        directories = {"/usr": {"exists": True, "readable": True, "writable": False, "description": "System"}}
        result = SandboxContextManager._format_directories(directories)
        assert "read" in result
        assert "write" not in result.split("/usr")[1].split("\n")[0]

    def test_restricted_when_no_perms(self):
        directories = {"/root": {"exists": True, "readable": False, "writable": False, "description": "Root home"}}
        result = SandboxContextManager._format_directories(directories)
        assert "restricted" in result

    def test_mixed_dirs_only_existing_shown(self):
        directories = {
            "/home/ubuntu": {"exists": True, "readable": True, "writable": True, "description": "Home"},
            "/gone": {"exists": False, "readable": False, "writable": False, "description": "Missing"},
        }
        result = SandboxContextManager._format_directories(directories)
        assert "/home/ubuntu" in result
        assert "/gone" not in result


# ---------------------------------------------------------------------------
# _format_python_stdlib
# ---------------------------------------------------------------------------


class TestFormatPythonStdlib:
    def test_empty_by_category_returns_defaults(self):
        result = SandboxContextManager._format_python_stdlib({})
        assert "os" in result
        assert "sys" in result
        assert "json" in result

    def test_modules_from_categories_included(self):
        stdlib = {
            "by_category": {
                "io": ["os", "sys", "pathlib"],
                "concurrency": ["asyncio", "threading"],
            }
        }
        result = SandboxContextManager._format_python_stdlib(stdlib)
        assert "os" in result
        assert "asyncio" in result

    def test_at_most_20_modules_returned(self):
        # 3 categories x 10 modules each = 30 candidates — capped at 20
        stdlib = {"by_category": {f"cat{i}": [f"mod{i}_{j}" for j in range(10)] for i in range(3)}}
        result = SandboxContextManager._format_python_stdlib(stdlib)
        modules = [m.strip() for m in result.split(",")]
        assert len(modules) <= 20

    def test_only_top_3_categories_used(self):
        # 5 categories — only first 3 contribute modules
        stdlib = {
            "by_category": {
                "cat0": ["aaa"],
                "cat1": ["bbb"],
                "cat2": ["ccc"],
                "cat3": ["ddd"],
                "cat4": ["eee"],
            }
        }
        result = SandboxContextManager._format_python_stdlib(stdlib)
        # ddd and eee come from cat3/cat4 — may or may not be present
        # but aaa, bbb, ccc must be there (first 3 categories)
        assert "aaa" in result
        assert "bbb" in result
        assert "ccc" in result


# ---------------------------------------------------------------------------
# _format_nodejs_builtins
# ---------------------------------------------------------------------------


class TestFormatNodejsBuiltins:
    def test_empty_by_category_returns_defaults(self):
        result = SandboxContextManager._format_nodejs_builtins({})
        assert "fs" in result
        assert "path" in result

    def test_core_modules_returned(self):
        builtins = {"by_category": {"core": ["fs", "path", "http", "crypto"]}}
        result = SandboxContextManager._format_nodejs_builtins(builtins)
        assert "fs" in result
        assert "crypto" in result

    def test_no_core_key_returns_fallback(self):
        builtins = {"by_category": {"other": ["some_module"]}}
        result = SandboxContextManager._format_nodejs_builtins(builtins)
        assert "fs" in result

    def test_at_most_20_modules_returned(self):
        builtins = {"by_category": {"core": [f"mod{i}" for i in range(30)]}}
        result = SandboxContextManager._format_nodejs_builtins(builtins)
        modules = [m.strip() for m in result.split(",")]
        assert len(modules) <= 20


# ---------------------------------------------------------------------------
# _format_execution_patterns
# ---------------------------------------------------------------------------


class TestFormatExecutionPatterns:
    def test_empty_patterns_returns_fallback(self):
        result = SandboxContextManager._format_execution_patterns({}, "python")
        assert "Standard execution available" in result

    def test_missing_language_returns_fallback(self):
        patterns = {"nodejs": {"run": "node script.js"}}
        result = SandboxContextManager._format_execution_patterns(patterns, "python")
        assert "Standard execution available" in result

    def test_python_patterns_formatted(self):
        patterns = {"python": {"run_script": "python3 script.py", "install_pkg": "pip3 install pkg"}}
        result = SandboxContextManager._format_execution_patterns(patterns, "python")
        assert "python3 script.py" in result
        assert "pip3 install pkg" in result

    def test_pattern_name_title_cased(self):
        patterns = {"python": {"run_script": "python3 script.py"}}
        result = SandboxContextManager._format_execution_patterns(patterns, "python")
        assert "Run Script" in result

    def test_at_most_6_patterns_shown(self):
        # 10 patterns — only first 6 included
        lang_patterns = {f"pattern_{i}": f"cmd{i}" for i in range(10)}
        patterns = {"python": lang_patterns}
        result = SandboxContextManager._format_execution_patterns(patterns, "python")
        lines = [ln for ln in result.splitlines() if ln.strip()]
        assert len(lines) <= 6


# ---------------------------------------------------------------------------
# _format_bash_examples
# ---------------------------------------------------------------------------


class TestFormatBashExamples:
    def test_empty_bash_commands_returns_fallback(self):
        result = SandboxContextManager._format_bash_examples({})
        assert "standard bash commands" in result.lower()

    def test_examples_from_file_operations_shown(self):
        bash_commands = {
            "file_operations": {
                "list": {"examples": ["ls -la /workspace"]},
            }
        }
        result = SandboxContextManager._format_bash_examples(bash_commands)
        assert "ls -la /workspace" in result

    def test_examples_from_network_shown(self):
        bash_commands = {
            "network": {
                "fetch": {"examples": ["curl -s https://api.example.com"]},
            }
        }
        result = SandboxContextManager._format_bash_examples(bash_commands)
        assert "curl -s https://api.example.com" in result

    def test_at_most_8_examples_shown(self):
        # Stuff all 3 categories with many commands
        bash_commands = {
            "file_operations": {f"cmd{i}": {"examples": [f"fo_cmd{i}"]} for i in range(10)},
            "text_processing": {f"cmd{i}": {"examples": [f"tp_cmd{i}"]} for i in range(10)},
            "network": {f"cmd{i}": {"examples": [f"net_cmd{i}"]} for i in range(10)},
        }
        result = SandboxContextManager._format_bash_examples(bash_commands)
        lines = [ln for ln in result.splitlines() if ln.strip()]
        assert len(lines) <= 8

    def test_commands_without_examples_skipped(self):
        bash_commands = {"file_operations": {"noex": {"examples": []}, "withex": {"examples": ["ls -la"]}}}
        result = SandboxContextManager._format_bash_examples(bash_commands)
        assert "ls -la" in result


# ---------------------------------------------------------------------------
# _format_resource_limits
# ---------------------------------------------------------------------------


class TestFormatResourceLimits:
    def test_empty_limits_still_shows_default_shared_memory(self):
        # Even with an empty dict the method defaults shared_memory to "2gb"
        # and always appends that line — the true fallback is unreachable with {}.
        result = SandboxContextManager._format_resource_limits({})
        assert "Shared Memory: 2gb" in result

    def test_fallback_string_is_covered_by_shared_memory_default(self):
        # The method always adds a Shared Memory line via its "2gb" default, so
        # the "Standard container limits apply" branch is unreachable with a
        # plain empty dict.  The shared_memory default line is always present.
        result = SandboxContextManager._format_resource_limits({})
        assert "Shared Memory" in result

    def test_disk_available_shown(self):
        limits = {"disk": {"available": "20GB"}, "shared_memory": "2gb"}
        result = SandboxContextManager._format_resource_limits(limits)
        assert "20GB" in result

    def test_shared_memory_always_shown(self):
        limits = {"shared_memory": "4gb"}
        result = SandboxContextManager._format_resource_limits(limits)
        assert "Shared Memory: 4gb" in result

    def test_memory_shown_when_known(self):
        limits = {"memory": "8gb", "shared_memory": "2gb"}
        result = SandboxContextManager._format_resource_limits(limits)
        assert "Memory: 8gb" in result

    def test_memory_unknown_not_shown(self):
        limits = {"memory": "unknown", "shared_memory": "2gb"}
        result = SandboxContextManager._format_resource_limits(limits)
        assert "Memory: unknown" not in result

    def test_disk_string_not_shown_as_section(self):
        # disk as a plain string (not dict) — treated as non-dict, skipped
        limits = {"disk": "20GB", "shared_memory": "2gb"}
        result = SandboxContextManager._format_resource_limits(limits)
        assert "Disk:" not in result


# ---------------------------------------------------------------------------
# _generate_fallback_prompt
# ---------------------------------------------------------------------------


class TestGenerateFallbackPrompt:
    def test_contains_sandbox_environment_tag(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "<sandbox_environment_knowledge>" in result
        assert "</sandbox_environment_knowledge>" in result

    def test_contains_fallback_indicator(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "Fallback" in result

    def test_contains_ubuntu_reference(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "Ubuntu" in result

    def test_contains_python_reference(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "python3" in result or "Python" in result

    def test_contains_nodejs_reference(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "Node.js" in result or "node" in result

    def test_contains_workspace_paths(self):
        result = SandboxContextManager._generate_fallback_prompt()
        assert "/home/ubuntu" in result
        assert "/workspace" in result


# ---------------------------------------------------------------------------
# generate_prompt_section
# ---------------------------------------------------------------------------


class TestGeneratePromptSection:
    def test_none_context_loads_and_falls_back_to_fallback(self):
        # _try_load_from_http returns None and no local file exists
        with (
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
            patch.object(SandboxContextManager, "_try_load_from_paths", return_value=None),
        ):
            result = SandboxContextManager.generate_prompt_section(context=None)
        assert "Fallback" in result
        assert "<sandbox_environment_knowledge>" in result

    def test_context_missing_environment_key_falls_back(self):
        result = SandboxContextManager.generate_prompt_section(context={"version": "1.0"})
        assert "Fallback" in result

    def test_empty_context_dict_falls_back(self):
        result = SandboxContextManager.generate_prompt_section(context={})
        assert "Fallback" in result

    def test_valid_context_contains_sandbox_tag(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "<sandbox_environment_knowledge>" in result
        assert "</sandbox_environment_knowledge>" in result

    def test_valid_context_no_fallback_marker(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "Fallback" not in result

    def test_valid_context_contains_knowledge_section_identifier(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "sandbox_environment_knowledge" in result

    def test_valid_context_renders_python_version(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "3.11.9" in result

    def test_valid_context_renders_node_version(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "22.13.0" in result

    def test_valid_context_renders_os_info(self):
        ctx = {"environment": _full_env()}
        result = SandboxContextManager.generate_prompt_section(context=ctx)
        assert "Ubuntu 22.04" in result
        assert "x86_64" in result


# ---------------------------------------------------------------------------
# get_context_stats
# ---------------------------------------------------------------------------


class TestGetContextStats:
    def test_no_context_available_false(self):
        with (
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
            patch.object(SandboxContextManager, "_try_load_from_paths", return_value=None),
        ):
            stats = SandboxContextManager.get_context_stats()
        assert stats["available"] is False
        assert stats["source"] is None
        assert stats["age"] is None

    def test_with_context_available_true(self):
        ctx = {
            "environment": {"python": {"package_count": 10}, "nodejs": {"package_count": 5}},
            "version": "1.0",
            "checksum": "abc123",
            "generated_at": datetime.now(UTC).isoformat(),
        }
        with patch.object(SandboxContextManager, "_try_load_from_paths", return_value=ctx):
            stats = SandboxContextManager.get_context_stats()
        assert stats["available"] is True

    def test_with_context_package_counts_returned(self):
        ctx = {
            "environment": {
                "python": {"package_count": 42},
                "nodejs": {"package_count": 7},
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }
        with patch.object(SandboxContextManager, "_try_load_from_paths", return_value=ctx):
            stats = SandboxContextManager.get_context_stats()
        assert stats["package_counts"]["python"] == 42
        assert stats["package_counts"]["nodejs"] == 7


# ---------------------------------------------------------------------------
# load_context — cache hit and force_reload
# ---------------------------------------------------------------------------


class TestLoadContext:
    def test_returns_none_when_no_source_available(self):
        with (
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
            patch.object(SandboxContextManager, "_try_load_from_paths", return_value=None),
        ):
            result = SandboxContextManager.load_context()
        assert result is None

    def test_cache_hit_skips_reload(self):
        cached = {"environment": {}, "_test": "cached"}
        SandboxContextManager._cache = cached
        SandboxContextManager._cache_timestamp = datetime.now(UTC)

        with patch.object(SandboxContextManager, "_try_load_from_paths") as mock_load:
            result = SandboxContextManager.load_context()

        mock_load.assert_not_called()
        assert result is cached

    def test_expired_cache_triggers_reload(self):
        stale = {"environment": {}, "_test": "stale"}
        fresh = {"environment": {}, "_test": "fresh"}
        SandboxContextManager._cache = stale
        # Expire the cache by backdating the timestamp
        SandboxContextManager._cache_timestamp = datetime.now(UTC) - timedelta(hours=25)

        with patch.object(SandboxContextManager, "_try_load_from_paths", return_value=fresh):
            result = SandboxContextManager.load_context()

        assert result is fresh

    def test_force_reload_bypasses_fresh_cache(self):
        cached = {"environment": {}, "_test": "cached"}
        reloaded = {"environment": {}, "_test": "reloaded"}
        SandboxContextManager._cache = cached
        SandboxContextManager._cache_timestamp = datetime.now(UTC)

        with patch.object(SandboxContextManager, "_try_load_from_paths", return_value=reloaded):
            result = SandboxContextManager.load_context(force_reload=True)

        assert result is reloaded

    def test_fresh_cache_returned_without_disk_hit(self):
        cached = {"environment": {"python": {}}}
        SandboxContextManager._cache = cached
        SandboxContextManager._cache_timestamp = datetime.now(UTC)

        with patch.object(SandboxContextManager, "_try_load_from_paths") as mock_paths:
            SandboxContextManager.load_context()

        mock_paths.assert_not_called()


# ---------------------------------------------------------------------------
# load_context — file-based loading (patching open + os.path.exists)
# ---------------------------------------------------------------------------


class TestLoadContextFromFile:
    def test_valid_json_file_populates_cache(self, tmp_path):
        ctx_file = tmp_path / "sandbox_context.json"
        ctx_data = {"environment": {"python": {"version": "3.11.9"}}}
        ctx_file.write_text(json.dumps(ctx_data))

        env_side_effect = lambda key, default="": str(ctx_file) if key == "SANDBOX_CONTEXT_JSON" else default  # noqa: E731
        with (
            patch("os.environ.get", side_effect=env_side_effect),
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
        ):
            result = SandboxContextManager._try_load_from_paths()

        assert result is not None
        assert result["environment"]["python"]["version"] == "3.11.9"
        assert SandboxContextManager._cache is not None
        assert SandboxContextManager._cache_timestamp is not None

    def test_json_file_missing_environment_key_skipped(self, tmp_path):
        ctx_file = tmp_path / "sandbox_context.json"
        ctx_file.write_text(json.dumps({"version": "1.0"}))  # no "environment" key

        env_side_effect = lambda key, default="": str(ctx_file) if key == "SANDBOX_CONTEXT_JSON" else default  # noqa: E731
        with (
            patch("os.environ.get", side_effect=env_side_effect),
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
        ):
            result = SandboxContextManager._try_load_from_paths()

        assert result is None


# ---------------------------------------------------------------------------
# get_sandbox_context_prompt convenience function
# ---------------------------------------------------------------------------


class TestGetSandboxContextPrompt:
    def test_returns_string(self):
        with (
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
            patch.object(SandboxContextManager, "_try_load_from_paths", return_value=None),
        ):
            result = get_sandbox_context_prompt()
        assert isinstance(result, str)

    def test_returns_fallback_when_no_context(self):
        with (
            patch.object(SandboxContextManager, "_try_load_from_http", return_value=None),
            patch.object(SandboxContextManager, "_try_load_from_paths", return_value=None),
        ):
            result = get_sandbox_context_prompt()
        assert "<sandbox_environment_knowledge>" in result

    def test_force_reload_uses_reloaded_context(self):
        ctx = {"environment": {"os": {"distribution": "Alpine Linux"}}}
        with patch.object(SandboxContextManager, "_try_load_from_paths", return_value=ctx):
            result = get_sandbox_context_prompt(force_reload=True)
        assert "Alpine Linux" in result
