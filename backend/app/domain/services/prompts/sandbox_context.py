"""
Sandbox Context Integration for Agent System Prompts

Provides pre-loaded environment knowledge to agents, eliminating the need
for exploratory discovery commands and reducing token waste.

Author: Pythinker Team
Version: 1.0.0
"""

import contextlib
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class SandboxContextManager:
    """Manages sandbox environment context for agent initialization"""

    # Cache context for 24 hours to avoid repeated file reads
    _cache: dict[str, Any] | None = None
    _cache_timestamp: datetime | None = None
    _cache_ttl = timedelta(hours=24)

    @classmethod
    def load_context(cls, force_reload: bool = False) -> dict[str, Any] | None:
        """
        Load sandbox environment context from JSON file.

        Args:
            force_reload: Force reload from disk even if cached

        Returns:
            Environment context dictionary or None if unavailable
        """
        # Return cached context if available and fresh
        if not force_reload and cls._cache and cls._cache_timestamp:
            age = datetime.utcnow() - cls._cache_timestamp
            if age < cls._cache_ttl:
                return cls._cache

        # Attempt to load context from file (check multiple locations including fallback)
        context_paths = [
            "/app/sandbox_context.json",  # Default sandbox location
            os.environ.get("SANDBOX_CONTEXT_JSON", ""),  # Environment override
            os.path.expanduser("~/sandbox_context.json"),  # Fallback when /app not writable
        ]

        for path in context_paths:
            if not path or not os.path.exists(path):
                continue

            try:
                with open(path) as f:
                    context = json.load(f)

                # Validate structure
                if "environment" not in context:
                    logger.warning(f"Invalid context structure in {path}")
                    continue

                # Update cache
                cls._cache = context
                cls._cache_timestamp = datetime.utcnow()

                logger.info(f"Loaded sandbox context from {path}")
                return context

            except Exception as e:
                logger.error(f"Failed to load context from {path}: {e}")

        logger.warning("No sandbox context available - agents will use default environment knowledge")
        return None

    @classmethod
    def generate_prompt_section(cls, context: dict[str, Any] | None = None) -> str:
        """
        Generate a concise prompt section with pre-loaded environment knowledge.

        This section replaces exploratory commands with static knowledge, saving tokens
        and reducing latency.

        Args:
            context: Environment context (loads automatically if not provided)

        Returns:
            Formatted prompt section ready for injection into system prompt
        """
        if context is None:
            context = cls.load_context()

        if not context or "environment" not in context:
            return cls._generate_fallback_prompt()

        env = context["environment"]

        # Build concise, agent-optimized prompt
        return """
<sandbox_environment_knowledge>
**PRE-LOADED ENVIRONMENT CONTEXT**

You have complete knowledge of your sandbox environment. DO NOT use exploratory commands
like "python3 --version", "which git", or "pip list" - this information is already known.

## System Configuration

- **OS:** {os_dist} ({os_arch})
- **User:** {user} (home: {home}, sudo: yes)
- **Shell:** {shell}
- **Key ENV vars:** PATH, HOME, DISPLAY, PYTHON_VERSION, NODE_VERSION

## Python Environment

- **Version:** {python_version}
- **Interpreter:** {python_path}
- **Package Manager:** {pip_version}

### Pre-installed Python Packages ({python_pkg_count} total)

Key packages available without installation:
{python_packages}

### Python Standard Library ({python_stdlib_count} modules built-in)

NO pip install needed for: {python_stdlib_modules}

## Node.js Environment

- **Node:** {node_version}
- **Package Managers:** npm ({npm_version}), pnpm ({pnpm_version}), yarn ({yarn_version})

Global packages installed: {node_pkg_count}

### Node.js Built-in Modules ({nodejs_builtins_count} modules built-in)

NO npm install needed for: {nodejs_builtin_modules}

## System Tools

**Development:** {dev_tools}
**Text Processing:** {text_tools}
**Network:** {network_tools}
**Compression:** {compression_tools}

## Browser Automation

{browser_info}

## File System & Workspaces

{directories}

## Common Command Patterns (Use These Directly)

### Python Execution
{python_patterns}

### Node.js Execution
{nodejs_patterns}

### Bash Examples (with correct flags)
{bash_examples}

## Service Endpoints (Internal)

- VNC Server: localhost:5900 (WebSocket: 5901)
- Chrome DevTools: localhost:9222
- Code Server: localhost:8081

## Resource Limits

{resource_limits}

## Diagnostic Capabilities (Pre-installed)

For system diagnostics and benchmarks, use these immediately:
- **psutil**: CPU, memory, disk, network, processes (INSTALLED - no pip needed)
- **platform**: OS info, architecture, Python version (STDLIB)
- **subprocess**: Execute commands, capture output (STDLIB)
- **json**: Structured output formatting (STDLIB)
- **time/timeit**: Performance measurement (STDLIB)
- **hashlib**: CPU benchmark hashing (STDLIB)
- **os**: Environment variables, file system info (STDLIB)

### Quick Diagnostic Script (copy-paste ready):
```python
import psutil, platform, json
print(json.dumps({{
    "cpu": psutil.cpu_count(),
    "ram_gb": round(psutil.virtual_memory().total/1024**3, 1),
    "disk_percent": psutil.disk_usage('/').percent,
    "os": platform.system(),
    "arch": platform.machine(),
    "python": platform.python_version()
}}, indent=2))
```

## Important Usage Notes

1. **No Exploration Needed:** All tools and packages listed above are confirmed available
2. **Use Built-in Modules First:** Python stdlib and Node.js builtins require NO installation
3. **Install Before Use:** For packages NOT listed, use `pip3 install` or `npm install` first
4. **Use Command Patterns:** Reference the examples above for correct syntax and flags
5. **Working Directory:** Start in /home/ubuntu, use /workspace for user code
6. **Internet Access:** Full internet connectivity available

**Action Mandate:** Use this knowledge immediately. Do not verify environment state unless
debugging a specific failure. Reference command patterns above instead of exploring.

</sandbox_environment_knowledge>
""".format(
            os_dist=env.get("os", {}).get("distribution", "Ubuntu 22.04"),
            os_arch=env.get("os", {}).get("architecture", "x86_64"),
            user=env.get("os", {}).get("user", "ubuntu"),
            home=env.get("os", {}).get("home", "/home/ubuntu"),
            shell=env.get("os", {}).get("shell", "/bin/bash"),
            python_version=env.get("python", {}).get("version", "Unknown"),
            python_path=env.get("python", {}).get("path", "/usr/bin/python3"),
            pip_version=env.get("python", {}).get("pip_version", "Unknown"),
            python_pkg_count=env.get("python", {}).get("package_count", 0),
            python_packages=cls._format_python_packages(env.get("python", {})),
            python_stdlib_count=env.get("python_stdlib", {}).get("total_count", 0),
            python_stdlib_modules=cls._format_python_stdlib(env.get("python_stdlib", {})),
            node_version=env.get("nodejs", {}).get("version", "Unknown"),
            npm_version=env.get("nodejs", {}).get("npm_version", "Unknown"),
            pnpm_version=env.get("nodejs", {}).get("pnpm_version", "Unknown"),
            yarn_version=env.get("nodejs", {}).get("yarn_version", "Unknown"),
            node_pkg_count=env.get("nodejs", {}).get("package_count", 0),
            nodejs_builtins_count=env.get("nodejs_builtins", {}).get("total_count", 0),
            nodejs_builtin_modules=cls._format_nodejs_builtins(env.get("nodejs_builtins", {})),
            dev_tools=", ".join(env.get("system_tools", {}).get("development", {}).keys()),
            text_tools=", ".join(env.get("system_tools", {}).get("text_processing", {}).keys()),
            network_tools=", ".join(env.get("system_tools", {}).get("network", {}).keys()),
            compression_tools=", ".join(env.get("system_tools", {}).get("compression", {}).keys()),
            browser_info=cls._format_browser_info(env.get("browser", {})),
            directories=cls._format_directories(env.get("directories", {})),
            python_patterns=cls._format_execution_patterns(env.get("execution_patterns", {}), "python"),
            nodejs_patterns=cls._format_execution_patterns(env.get("execution_patterns", {}), "nodejs"),
            bash_examples=cls._format_bash_examples(env.get("bash_commands", {})),
            resource_limits=cls._format_resource_limits(env.get("resource_limits", {})),
        )

    @classmethod
    def _format_python_packages(cls, python_env: dict[str, Any]) -> str:
        """Format Python packages for prompt"""
        key_packages = python_env.get("key_packages", {})
        if not key_packages:
            return "- Standard library only"

        lines = []
        for pkg, version in sorted(key_packages.items())[:15]:  # Top 15 to save tokens
            lines.append(f"- {pkg} ({version})")

        total = python_env.get("package_count", 0)
        shown = len(lines)
        if total > shown:
            lines.append(f"- ... and {total - shown} more packages")

        return "\n".join(lines)

    @classmethod
    def _format_browser_info(cls, browser_env: dict[str, Any]) -> str:
        """Format browser capabilities for prompt"""
        info = []

        chromium = browser_env.get("chromium", {})
        if chromium.get("available"):
            info.append(f"- Chromium: {chromium.get('version', 'Available')}")

        playwright = browser_env.get("playwright", {})
        if playwright.get("available"):
            browsers = ", ".join(playwright.get("browsers", []))
            stealth = " (stealth mode enabled)" if playwright.get("stealth_mode") else ""
            info.append(f"- Playwright: {browsers}{stealth}")

        return "\n".join(info) if info else "- Basic browser automation available"

    @classmethod
    def _format_directories(cls, directories: dict[str, Any]) -> str:
        """Format directory information for prompt"""
        lines = []
        for path, info in directories.items():
            if not info.get("exists"):
                continue

            perms = []
            if info.get("readable"):
                perms.append("read")
            if info.get("writable"):
                perms.append("write")

            perm_str = "+".join(perms) if perms else "restricted"
            desc = info.get("description", "")

            lines.append(f"- `{path}`: {desc} ({perm_str})")

        return "\n".join(lines) if lines else "- Standard filesystem layout"

    @classmethod
    def _format_python_stdlib(cls, stdlib: dict[str, Any]) -> str:
        """Format Python standard library modules for prompt"""
        by_category = stdlib.get("by_category", {})
        if not by_category:
            return "os, sys, re, json, datetime, pathlib, subprocess, asyncio"

        # Collect modules from top categories
        all_modules = []
        for _category, modules in list(by_category.items())[:3]:  # Top 3 categories
            all_modules.extend(modules[:8])  # Top 8 from each

        return ", ".join(all_modules[:20])  # Limit to 20 total to save tokens

    @classmethod
    def _format_nodejs_builtins(cls, builtins: dict[str, Any]) -> str:
        """Format Node.js built-in modules for prompt"""
        by_category = builtins.get("by_category", {})
        if not by_category:
            return "fs, path, http, https, crypto, buffer, stream, util"

        # Get core modules
        core = by_category.get("core", [])
        return ", ".join(core[:20]) if core else "fs, path, http, https, crypto"

    @classmethod
    def _format_execution_patterns(cls, patterns: dict[str, Any], language: str) -> str:
        """Format execution patterns for a specific language"""
        lang_patterns = patterns.get(language, {})
        if not lang_patterns:
            return "- Standard execution available"

        lines = []
        for pattern_name, command in list(lang_patterns.items())[:6]:  # Top 6 patterns
            display_name = pattern_name.replace("_", " ").title()
            lines.append(f"- {display_name}: `{command}`")

        return "\n".join(lines)

    @classmethod
    def _format_bash_examples(cls, bash_commands: dict[str, Any]) -> str:
        """Format bash command examples for prompt"""
        if not bash_commands:
            return "- Use standard bash commands with man pages for reference"

        lines = []
        categories = ["file_operations", "text_processing", "network"]

        for category in categories:
            cat_commands = bash_commands.get(category, {})
            for _cmd_name, cmd_info in list(cat_commands.items())[:2]:  # Top 2 per category
                examples = cmd_info.get("examples", [])
                if examples:
                    lines.append(f"- `{examples[0]}`")

        return "\n".join(lines[:8])  # Limit to 8 total examples

    @classmethod
    def _format_resource_limits(cls, limits: dict[str, Any]) -> str:
        """Format resource limits for prompt"""
        lines = []

        if "disk" in limits and isinstance(limits["disk"], dict):
            disk = limits["disk"]
            lines.append(f"- Disk: {disk.get('available', 'unknown')} available")

        shm = limits.get("shared_memory", "2gb")
        lines.append(f"- Shared Memory: {shm}")

        memory = limits.get("memory", "unknown")
        if memory != "unknown":
            lines.append(f"- Memory: {memory}")

        return "\n".join(lines) if lines else "- Standard container limits apply"

    @classmethod
    def _generate_fallback_prompt(cls) -> str:
        """Generate fallback prompt when context file is unavailable"""
        return """
<sandbox_environment_knowledge>
**ENVIRONMENT CONTEXT** (Fallback - context file unavailable)

## System Configuration

- **OS:** Ubuntu 22.04 LTS (x86_64)
- **User:** ubuntu (sudo access enabled)
- **Python:** 3.11.x with pip
- **Node.js:** 22.13.0 with npm, pnpm, yarn

## Common Pre-installed Tools

- **Development:** git, gh (GitHub CLI), gcc, make
- **Text Processing:** grep, sed, awk, jq, ripgrep
- **Network:** curl, wget, netstat
- **Browser:** Chromium, Playwright (chromium, firefox, webkit)

## Python Standard Library (Built-in)

Common modules available without pip install:
os, sys, re, json, datetime, pathlib, subprocess, asyncio, collections, itertools

## Node.js Built-ins (No npm install needed)

fs, path, http, https, crypto, buffer, stream, util, events, url

## Common Command Patterns

**Python:** `python3 script.py`, `pip3 install package`, `pytest tests/`
**Node.js:** `node script.js`, `npm install package`, `jest tests/`
**Bash:** `grep -rn 'pattern' .`, `curl -s https://api.example.com`, `jq '.' file.json`

## Diagnostic Capabilities

For system diagnostics and benchmarks:
- **psutil**: CPU, memory, disk, network (install with `pip3 install psutil`)
- **platform, os, subprocess, json, time, hashlib**: Built-in (STDLIB)

Quick diagnostic pattern:
```python
import platform, os, json
print(json.dumps({"os": platform.system(), "arch": platform.machine()}, indent=2))
```

## Workspaces

- `/home/ubuntu` - Default home directory (read+write)
- `/workspace` - User code execution workspace (read+write)
- `/tmp` - Temporary files (read+write)

**Note:** For specific package versions, use `pip list` or `npm list -g` as needed.

</sandbox_environment_knowledge>
"""

    @classmethod
    def get_context_stats(cls) -> dict[str, Any]:
        """Get statistics about current context"""
        context = cls.load_context()

        if not context:
            return {
                "available": False,
                "source": None,
                "age": None,
            }

        generated_at = context.get("generated_at")
        age = None
        if generated_at:
            with contextlib.suppress(Exception):
                gen_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                age = datetime.utcnow() - gen_time

        return {
            "available": True,
            "source": "cached" if cls._cache else "disk",
            "version": context.get("version"),
            "checksum": context.get("checksum"),
            "generated_at": generated_at,
            "age_hours": age.total_seconds() / 3600 if age else None,
            "package_counts": {
                "python": context.get("environment", {}).get("python", {}).get("package_count", 0),
                "nodejs": context.get("environment", {}).get("nodejs", {}).get("package_count", 0),
            },
        }


# Convenience function for easy import
def get_sandbox_context_prompt(force_reload: bool = False) -> str:
    """
    Get the sandbox environment context prompt section.

    Args:
        force_reload: Force reload context from disk

    Returns:
        Formatted prompt section for injection into system prompts
    """
    manager = SandboxContextManager()
    context = manager.load_context(force_reload=force_reload) if force_reload else None
    return manager.generate_prompt_section(context)


# Auto-load context on module import for caching
with contextlib.suppress(BaseException):
    SandboxContextManager.load_context()
