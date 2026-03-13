#!/usr/bin/env python3
"""
Sandbox Environment Context Generator

Automatically inventories the sandbox environment and generates a structured
context file that agents can load to understand their capabilities without
requiring exploratory discovery.

This eliminates token waste from commands like:
- "what python version is installed?"
- "list available packages"
- "check if git is available"

Author: Pythinker Team
Version: 1.0.0
"""

import json
import subprocess
import sys
import os
import hashlib
from typing import Any, Dict, Optional
from datetime import datetime


class EnvironmentScanner:
    """Scans and documents the sandbox environment"""

    def __init__(self, output_path: str = "/app/sandbox_context.json"):
        self.output_path = output_path
        self.context = {
            "generated_at": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "environment": {},
        }

    def run_command(self, cmd: str, shell: bool = True) -> Optional[str]:
        """Execute command and return stdout, or None on error"""
        try:
            result = subprocess.run(
                cmd, shell=shell, capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            print(f"Error running command '{cmd}': {e}", file=sys.stderr)
            return None

    def scan_os_info(self) -> Dict[str, Any]:
        """Scan OS and kernel information"""
        return {
            "distribution": self.run_command("lsb_release -d | cut -f2-")
            or "Ubuntu 22.04",
            "kernel": self.run_command("uname -r"),
            "architecture": self.run_command("uname -m"),
            "hostname": self.run_command("hostname"),
            "user": os.environ.get("USER", "ubuntu"),
            "home": os.environ.get("HOME", "/home/ubuntu"),
            "shell": os.environ.get("SHELL", "/bin/bash"),
            "sandbox_version": os.environ.get("SANDBOX_VERSION", "dev"),
            "timezone": os.environ.get("TZ", "UTC"),
        }

    def scan_python_environment(self) -> Dict[str, Any]:
        """Scan Python installation and packages"""
        python_info = {
            "version": self.run_command("python3 --version"),
            "path": self.run_command("which python3"),
            "pip_version": self.run_command("pip3 --version"),
            "uv_version": self.run_command("uv --version"),
        }

        # Get installed packages
        pip_list = self.run_command("pip3 list --format=json")
        if pip_list:
            try:
                packages = json.loads(pip_list)
                python_info["installed_packages"] = {
                    pkg["name"]: pkg["version"] for pkg in packages
                }
                python_info["package_count"] = len(packages)
            except json.JSONDecodeError:
                python_info["installed_packages"] = {}

        # Key packages to highlight
        key_packages = [
            "fastapi",
            "uvicorn",
            "pydantic",
            "playwright",
            "playwright-stealth",
            "pytest",
            "black",
            "flake8",
            "mypy",
            "requests",
            "httpx",
            "aiohttp",
            "pandas",
            "numpy",
            "sqlalchemy",
        ]

        python_info["key_packages"] = {}
        for pkg in key_packages:
            if pip_list and pkg in python_info.get("installed_packages", {}):
                python_info["key_packages"][pkg] = python_info["installed_packages"][
                    pkg
                ]

        return python_info

    def scan_nodejs_environment(self) -> Dict[str, Any]:
        """Scan Node.js installation and global packages"""
        node_info = {
            "version": self.run_command("node --version"),
            "path": self.run_command("which node"),
            "npm_version": self.run_command("npm --version"),
            "pnpm_version": self.run_command("pnpm --version"),
            "yarn_version": self.run_command("yarn --version"),
        }

        # Get global npm packages
        npm_list = self.run_command("npm list -g --json --depth=0")
        if npm_list:
            try:
                packages = json.loads(npm_list)
                deps = packages.get("dependencies", {})
                node_info["global_packages"] = {
                    name: data.get("version", "unknown") for name, data in deps.items()
                }
                node_info["package_count"] = len(deps)
            except json.JSONDecodeError:
                node_info["global_packages"] = {}

        return node_info

    def scan_system_tools(self) -> Dict[str, Any]:
        """Scan available system tools and utilities"""
        tools = {
            "shell": {},
            "development": {},
            "version_control": {},
            "text_processing": {},
            "network": {},
            "compression": {},
        }

        # Shell utilities
        shell_tools = ["bash", "sh", "zsh", "sudo", "bc"]
        for tool in shell_tools:
            version = self.run_command(f"which {tool}")
            if version:
                tools["shell"][tool] = {"available": True, "path": version}

        # Development tools
        dev_tools = {
            "git": "git --version",
            "gcc": "gcc --version | head -n1",
            "make": "make --version | head -n1",
            "gh": "gh --version | head -n1",
            "uv": "uv --version",
            "code-server": "code-server --version 2>/dev/null | head -n1",
        }
        for tool, cmd in dev_tools.items():
            result = self.run_command(cmd)
            if result:
                tools["development"][tool] = {
                    "available": True,
                    "version": result,
                    "path": self.run_command(f"which {tool}"),
                }

        # Version control
        git_config = {
            "installed": self.run_command("git --version") is not None,
            "version": self.run_command("git --version"),
        }
        tools["version_control"]["git"] = git_config

        # Text processing
        text_tools = ["grep", "sed", "awk", "jq", "ripgrep"]
        for tool in text_tools:
            path = self.run_command(f"which {tool}")
            if path:
                tools["text_processing"][tool] = {"available": True, "path": path}

        # Network tools
        net_tools = ["curl", "wget", "netstat", "ping", "nc"]
        for tool in net_tools:
            path = self.run_command(f"which {tool}")
            if path:
                tools["network"][tool] = {"available": True, "path": path}

        # Compression tools
        comp_tools = ["zip", "unzip", "tar", "gzip"]
        for tool in comp_tools:
            path = self.run_command(f"which {tool}")
            if path:
                tools["compression"][tool] = {"available": True, "path": path}

        return tools

    def scan_browser_environment(self) -> Dict[str, Any]:
        """Scan browser automation capabilities"""
        browser_info = {
            "chromium": {},
            "chrome_for_testing": {},
            "playwright": {},
        }

        # Check Chrome for Testing 128.0.6613.137 (primary sandbox browser)
        cft_path = "/opt/chrome-for-testing/chrome"
        cft_version = self.run_command(f"{cft_path} --version 2>/dev/null")
        if cft_version:
            browser_info["chrome_for_testing"] = {
                "available": True,
                "version": cft_version.strip(),
                "path": cft_path,
            }

        # Check Chromium (fallback for Playwright scripts)
        chromium_version = self.run_command("chromium --version")
        if chromium_version:
            browser_info["chromium"] = {
                "available": True,
                "version": chromium_version,
                "path": self.run_command("which chromium"),
            }

        # Check Playwright browsers
        playwright_browsers = self.run_command(
            "python3 -c \"import playwright; print('installed')\""
        )
        if playwright_browsers:
            browser_info["playwright"] = {
                "available": True,
                "browsers": ["chromium", "firefox", "webkit"],
                "stealth_mode": self.run_command(
                    "python3 -c \"import playwright_stealth; print('available')\""
                )
                == "available",
            }

        return browser_info

    def scan_sandbox_capabilities(self) -> Dict[str, Any]:
        """Document high-level sandbox capabilities"""
        addons_enabled = os.environ.get("SANDBOX_ADDONS_ENABLED", "0") == "1"
        return {
            "profile": "full" if addons_enabled else "minimal",
            "addons_enabled": addons_enabled,
            "streaming_mode": "cdp_only",
            "execution": {
                "python": True,
                "nodejs": True,
                "shell": True,
                "browser_automation": True,
            },
            "network": {
                "internet_access": True,
                "http_client": ["curl", "wget", "httpx", "requests"],
            },
            "file_operations": {
                "read": True,
                "write": True,
                "workspace": "/workspace",
                "home": "/home/ubuntu",
            },
            "services": {
                "chrome_devtools": {
                    "enabled": True,
                    "port": 9222,
                },
            },
            "resource_limits": {
                "description": "Containerized environment with resource limits",
                "shared_memory": os.environ.get("SHM_SIZE", "2gb"),
            },
        }

    def scan_directory_structure(self) -> Dict[str, Any]:
        """Scan important directories"""
        important_paths = {
            "/workspace": "User code execution workspace",
            "/home/ubuntu": "Default user home directory",
            "/app": "Sandbox service application",
            "/tmp": "Temporary files",
        }

        structure = {}
        for path, description in important_paths.items():
            if os.path.exists(path):
                structure[path] = {
                    "exists": True,
                    "description": description,
                    "writable": os.access(path, os.W_OK),
                    "readable": os.access(path, os.R_OK),
                }

        return structure

    def scan_bash_commands(self) -> Dict[str, Any]:
        """Catalog common bash commands with usage patterns"""
        commands = {
            "file_operations": {
                "ls": {
                    "flags": ["-la", "-lh", "-R", "-t"],
                    "examples": ["ls -la", "ls -lh /workspace", "ls -lt"],
                },
                "cat": {
                    "flags": ["-n", "-A", "-v"],
                    "examples": ["cat file.txt", "cat -n file.py"],
                },
                "grep": {
                    "flags": ["-r", "-i", "-n", "-v", "-E", "-A", "-B", "-C"],
                    "examples": [
                        "grep -rn 'pattern' .",
                        "grep -i 'error' logfile.txt",
                        "grep -E 'regex' file",
                    ],
                },
                "find": {
                    "flags": ["-name", "-type", "-mtime", "-size"],
                    "examples": [
                        "find . -name '*.py'",
                        "find /workspace -type f -mtime -1",
                        "find . -name '*.log' -delete",
                    ],
                },
                "sed": {
                    "flags": ["-i", "-n", "-e"],
                    "examples": [
                        "sed -i 's/old/new/g' file.txt",
                        "sed -n '1,10p' file.txt",
                    ],
                },
                "awk": {
                    "examples": [
                        "awk '{print $1}' file.txt",
                        "awk -F':' '{print $1}' /etc/passwd",
                    ]
                },
            },
            "text_processing": {
                "jq": {
                    "flags": ["-r", "-c", "-M", "-S"],
                    "examples": [
                        "jq '.' file.json",
                        "jq -r '.key' file.json",
                        "jq '.[] | select(.active)' data.json",
                    ],
                },
                "sort": {
                    "flags": ["-n", "-r", "-u", "-k"],
                    "examples": [
                        "sort file.txt",
                        "sort -n numbers.txt",
                        "sort -u -k2 data.txt",
                    ],
                },
                "uniq": {
                    "flags": ["-c", "-d", "-u"],
                    "examples": ["sort file.txt | uniq", "sort file.txt | uniq -c"],
                },
                "wc": {
                    "flags": ["-l", "-w", "-c"],
                    "examples": ["wc -l file.txt", "find . -name '*.py' | wc -l"],
                },
            },
            "network": {
                "curl": {
                    "flags": ["-X", "-H", "-d", "-o", "-s", "-L", "-k"],
                    "examples": [
                        "curl -s https://api.example.com",
                        "curl -X POST -H 'Content-Type: application/json' -d '{\"key\":\"value\"}' https://api.example.com",
                        "curl -L -o file.tar.gz https://example.com/file.tar.gz",
                    ],
                },
                "wget": {
                    "flags": ["-O", "-q", "-c", "-r"],
                    "examples": [
                        "wget -q https://example.com/file.tar.gz",
                        "wget -O output.html https://example.com",
                    ],
                },
            },
            "process_management": {
                "ps": {
                    "flags": ["aux", "-ef", "-p"],
                    "examples": ["ps aux | grep python", "ps -ef | grep node"],
                },
                "kill": {
                    "flags": ["-9", "-15", "-TERM", "-HUP"],
                    "examples": [
                        "kill -15 1234",
                        "kill -9 1234",
                        "pkill -f 'python script.py'",
                    ],
                },
                "top": {
                    "flags": ["-b", "-n"],
                    "examples": ["top -b -n 1", "top -p 1234"],
                },
            },
            "compression": {
                "tar": {
                    "flags": ["-czf", "-xzf", "-czvf", "-xzvf", "-tf"],
                    "examples": [
                        "tar -czf archive.tar.gz directory/",
                        "tar -xzf archive.tar.gz",
                        "tar -tf archive.tar.gz",
                    ],
                },
                "zip": {
                    "flags": ["-r", "-q"],
                    "examples": [
                        "zip -r archive.zip directory/",
                        "zip file.zip file.txt",
                    ],
                },
                "unzip": {
                    "flags": ["-q", "-l", "-d"],
                    "examples": [
                        "unzip archive.zip",
                        "unzip -l archive.zip",
                        "unzip archive.zip -d target_dir/",
                    ],
                },
            },
            "git": {
                "common": {
                    "examples": [
                        "git clone https://github.com/user/repo.git",
                        "git status",
                        "git add .",
                        "git commit -m 'message'",
                        "git push origin main",
                        "git pull",
                        "git branch",
                        "git checkout -b new-branch",
                        "git log --oneline -10",
                        "git diff",
                    ]
                }
            },
        }

        return commands

    def scan_python_stdlib(self) -> Dict[str, Any]:
        """List Python standard library modules (no pip install needed)"""
        # Major stdlib modules that agents commonly use
        stdlib_modules = {
            "core": [
                "os",
                "sys",
                "re",
                "json",
                "datetime",
                "time",
                "math",
                "random",
                "collections",
                "itertools",
                "functools",
                "operator",
                "typing",
            ],
            "file_io": [
                "pathlib",
                "shutil",
                "tempfile",
                "glob",
                "fnmatch",
                "io",
                "csv",
            ],
            "data": [
                "pickle",
                "shelve",
                "sqlite3",
                "hashlib",
                "hmac",
                "secrets",
                "uuid",
            ],
            "text": ["string", "textwrap", "difflib", "unicodedata"],
            "network": [
                "http.client",
                "urllib.request",
                "urllib.parse",
                "socket",
                "ssl",
                "email",
                "smtplib",
                "ftplib",
            ],
            "web": ["html.parser", "xml.etree.ElementTree", "json"],
            "concurrency": [
                "threading",
                "multiprocessing",
                "subprocess",
                "asyncio",
                "queue",
                "concurrent.futures",
            ],
            "system": [
                "argparse",
                "logging",
                "configparser",
                "getpass",
                "platform",
                "signal",
                "atexit",
                "traceback",
                "warnings",
                "contextlib",
            ],
            "testing": ["unittest", "doctest", "pdb", "timeit", "profile", "trace"],
            "utilities": [
                "base64",
                "binascii",
                "struct",
                "codecs",
                "copy",
                "pprint",
                "enum",
                "dataclasses",
                "abc",
                "weakref",
            ],
        }

        # Verify availability of key modules
        available_modules = {}
        for category, modules in stdlib_modules.items():
            available = []
            for module in modules:
                try:
                    __import__(module)
                    available.append(module)
                except ImportError:
                    pass
            if available:
                available_modules[category] = available

        return {
            "total_count": sum(len(mods) for mods in available_modules.values()),
            "by_category": available_modules,
            "note": "These modules are built-in and require no pip install",
        }

    def scan_nodejs_builtins(self) -> Dict[str, Any]:
        """List Node.js built-in modules (no npm install needed)"""
        builtin_modules = {
            "core": [
                "assert",
                "buffer",
                "child_process",
                "cluster",
                "crypto",
                "dgram",
                "dns",
                "domain",
                "events",
                "fs",
                "http",
                "http2",
                "https",
                "net",
                "os",
                "path",
                "perf_hooks",
                "process",
                "querystring",
                "readline",
                "repl",
                "stream",
                "string_decoder",
                "timers",
                "tls",
                "tty",
                "url",
                "util",
                "v8",
                "vm",
                "zlib",
            ],
            "file_system": ["fs", "fs/promises", "path"],
            "network": ["http", "https", "http2", "net", "dgram", "dns", "tls"],
            "streams": ["stream", "stream/promises", "stream/web"],
            "utilities": ["util", "url", "querystring", "events", "crypto"],
            "process": ["process", "child_process", "cluster", "worker_threads"],
        }

        return {
            "total_count": len(builtin_modules["core"]),
            "by_category": builtin_modules,
            "note": "These modules are built-in and require no npm install",
        }

    def scan_environment_variables(self) -> Dict[str, str]:
        """Scan important environment variables"""
        important_vars = [
            "PATH",
            "HOME",
            "USER",
            "SHELL",
            "TERM",
            "LANG",
            "LC_ALL",
            "DISPLAY",
            "PYTHON_VERSION",
            "NODE_VERSION",
            "NVM_DIR",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "PNPM_HOME",
        ]

        env_vars = {}
        for var in important_vars:
            value = os.environ.get(var)
            if value:
                env_vars[var] = value

        return env_vars

    def scan_execution_patterns(self) -> Dict[str, Any]:
        """Document common execution patterns for agents"""
        return {
            "python": {
                "run_script": "python3 script.py",
                "run_module": "python3 -m module_name",
                "run_with_args": "python3 script.py arg1 arg2",
                "pip_install": "pip3 install package_name",
                "pip_install_requirements": "pip3 install -r requirements.txt",
                "run_tests": "pytest tests/",
                "run_single_test": "pytest tests/test_file.py::test_function",
                "check_syntax": "python3 -m py_compile script.py",
                "format_code": "black script.py",
                "type_check": "mypy script.py",
            },
            "nodejs": {
                "run_script": "node script.js",
                "run_with_esm": "node --input-type=module script.mjs",
                "npm_install": "npm install package_name",
                "npm_install_dev": "npm install --save-dev package_name",
                "npm_install_deps": "npm install",
                "pnpm_install": "pnpm add package_name",
                "run_tests": "npm test",
                "run_jest": "jest tests/",
                "check_syntax": "node --check script.js",
                "format_code": "prettier --write script.js",
                "type_check": "tsc --noEmit",
            },
            "shell": {
                "make_executable": "chmod +x script.sh",
                "run_background": "nohup command &",
                "run_with_timeout": "timeout 30s command",
                "redirect_output": "command > output.txt 2>&1",
                "pipe_commands": "command1 | command2 | command3",
                "run_in_subshell": "(cd /path && command)",
                "check_exit_code": "command && echo 'success' || echo 'failed'",
            },
            "browser": {
                "playwright_python": "python3 -m playwright install chromium",
                "run_chromium_headless": "chromium --headless --disable-gpu --dump-dom https://example.com",
            },
        }

    def scan_resource_limits(self) -> Dict[str, Any]:
        """Scan container resource limits"""
        limits = {
            "memory": os.environ.get("MEMORY_LIMIT", "unknown"),
            "cpu": os.environ.get("CPU_LIMIT", "unknown"),
            "shared_memory": os.environ.get("SHM_SIZE", "2gb"),
        }

        # Try to get actual disk usage
        disk_usage = self.run_command(
            "df -h /workspace | tail -1 | awk '{print $2, $3, $4, $5}'"
        )
        if disk_usage:
            parts = disk_usage.split()
            if len(parts) == 4:
                limits["disk"] = {
                    "total": parts[0],
                    "used": parts[1],
                    "available": parts[2],
                    "use_percent": parts[3],
                }

        return limits

    def generate_checksum(self) -> str:
        """Generate checksum of current environment state"""
        # Use key versions to generate a checksum
        key_data = [
            self.run_command("python3 --version") or "",
            self.run_command("node --version") or "",
            self.run_command("uname -r") or "",
            str(datetime.utcnow().date()),  # Include date for daily regeneration
        ]
        return hashlib.sha256("".join(key_data).encode()).hexdigest()[:16]

    def scan_all(self) -> Dict[str, Any]:
        """Perform complete environment scan"""
        print("Scanning sandbox environment...", file=sys.stderr)

        self.context["environment"] = {
            "os": self.scan_os_info(),
            "python": self.scan_python_environment(),
            "nodejs": self.scan_nodejs_environment(),
            "system_tools": self.scan_system_tools(),
            "browser": self.scan_browser_environment(),
            "capabilities": self.scan_sandbox_capabilities(),
            "directories": self.scan_directory_structure(),
            "bash_commands": self.scan_bash_commands(),
            "python_stdlib": self.scan_python_stdlib(),
            "nodejs_builtins": self.scan_nodejs_builtins(),
            "environment_variables": self.scan_environment_variables(),
            "execution_patterns": self.scan_execution_patterns(),
            "resource_limits": self.scan_resource_limits(),
        }

        self.context["checksum"] = self.generate_checksum()

        print("Environment scan complete!", file=sys.stderr)
        return self.context

    def _resolve_writable_path(self, path: str) -> str:
        """Return path if writable, otherwise fall back to ~/."""
        try:
            # Check if we can write to the target path
            parent = os.path.dirname(path) or "."
            if os.access(path, os.W_OK) or (
                not os.path.exists(path) and os.access(parent, os.W_OK)
            ):
                return path
        except OSError:
            pass
        # Fall back to home directory
        fallback = os.path.join(os.path.expanduser("~"), os.path.basename(path))
        print(
            f"Warning: {path} not writable, falling back to {fallback}", file=sys.stderr
        )
        return fallback

    def save_json(self) -> None:
        """Save context as JSON"""
        resolved = self._resolve_writable_path(self.output_path)
        with open(resolved, "w") as f:
            json.dump(self.context, f, indent=2)
        print(f"Context saved to {resolved}", file=sys.stderr)

    def save_markdown(self, md_path: str = "/app/sandbox_context.md") -> None:
        """Save context as Markdown for human readability"""
        resolved = self._resolve_writable_path(md_path)
        md_content = self.generate_markdown()
        with open(resolved, "w") as f:
            f.write(md_content)
        print(f"Markdown context saved to {resolved}", file=sys.stderr)

    def generate_markdown(self) -> str:
        """Generate human-readable Markdown summary"""
        env = self.context["environment"]

        md = f"""# Sandbox Environment Context

**Generated:** {self.context["generated_at"]}
**Version:** {self.context["version"]}
**Checksum:** {self.context.get("checksum", "N/A")}

## Operating System

- **Distribution:** {env["os"].get("distribution", "Unknown")}
- **Kernel:** {env["os"].get("kernel", "Unknown")}
- **Architecture:** {env["os"].get("architecture", "Unknown")}
- **User:** {env["os"].get("user", "ubuntu")}
- **Home:** {env["os"].get("home", "/home/ubuntu")}

## Python Environment

- **Version:** {env["python"].get("version", "Unknown")}
- **Path:** {env["python"].get("path", "Unknown")}
- **Pip:** {env["python"].get("pip_version", "Unknown")}
- **Total Packages:** {env["python"].get("package_count", 0)}

### Key Python Packages

"""
        for pkg, version in env["python"].get("key_packages", {}).items():
            md += f"- **{pkg}:** {version}\n"

        md += f"""
## Node.js Environment

- **Version:** {env["nodejs"].get("version", "Unknown")}
- **NPM:** {env["nodejs"].get("npm_version", "Unknown")}
- **PNPM:** {env["nodejs"].get("pnpm_version", "Unknown")}
- **Yarn:** {env["nodejs"].get("yarn_version", "Unknown")}
- **Global Packages:** {env["nodejs"].get("package_count", 0)}

## Browser Automation

"""
        cft = env["browser"].get("chrome_for_testing", {})
        if cft.get("available"):
            md += f"- **Chrome for Testing:** {cft.get('version', '128.0.6613.137')}\n"

        chromium = env["browser"].get("chromium", {})
        if chromium.get("available"):
            md += f"- **Chromium:** {chromium.get('version', 'Available')}\n"

        playwright = env["browser"].get("playwright", {})
        if playwright.get("available"):
            md += f"- **Playwright:** Available (browsers: {', '.join(playwright.get('browsers', []))})\n"
            md += f"- **Stealth Mode:** {'Yes' if playwright.get('stealth_mode') else 'No'}\n"

        md += """
## System Tools

### Development Tools
"""
        for tool, info in env["system_tools"].get("development", {}).items():
            if info.get("available"):
                md += f"- **{tool}:** {info.get('version', 'Available')}\n"

        md += "\n### Text Processing\n"
        for tool in env["system_tools"].get("text_processing", {}).keys():
            md += f"- {tool}\n"

        md += "\n### Network Tools\n"
        for tool in env["system_tools"].get("network", {}).keys():
            md += f"- {tool}\n"

        md += """
## Sandbox Capabilities

### Execution
- Python scripts
- Node.js applications
- Shell commands
- Browser automation (Playwright, Puppeteer)

### Services
- **Live Preview:** CDP screencast/input via backend proxy (default)
- **Chrome DevTools Protocol:** Port 9222
- **Code Server:** Port 8081

### File System
"""
        for path, info in env["directories"].items():
            if info.get("exists"):
                perms = []
                if info.get("readable"):
                    perms.append("R")
                if info.get("writable"):
                    perms.append("W")
                md += f"- **{path}:** {info.get('description')} ({''.join(perms)})\n"

        md += """
## Execution Patterns

### Python Execution
"""
        for pattern, command in (
            env.get("execution_patterns", {}).get("python", {}).items()
        ):
            md += f"- **{pattern.replace('_', ' ').title()}:** `{command}`\n"

        md += "\n### Node.js Execution\n"
        for pattern, command in (
            env.get("execution_patterns", {}).get("nodejs", {}).items()
        ):
            md += f"- **{pattern.replace('_', ' ').title()}:** `{command}`\n"

        md += "\n### Shell Patterns\n"
        for pattern, command in (
            env.get("execution_patterns", {}).get("shell", {}).items()
        ):
            md += f"- **{pattern.replace('_', ' ').title()}:** `{command}`\n"

        md += (
            """
## Python Standard Library

**Total Built-in Modules:** """
            + str(env.get("python_stdlib", {}).get("total_count", 0))
            + """

No pip install needed for these modules:
"""
        )
        stdlib = env.get("python_stdlib", {}).get("by_category", {})
        for category, modules in list(stdlib.items())[:5]:  # Show top 5 categories
            md += f"\n**{category.replace('_', ' ').title()}:** {', '.join(modules[:10])}\n"

        md += (
            """
## Node.js Built-in Modules

**Total Built-in Modules:** """
            + str(env.get("nodejs_builtins", {}).get("total_count", 0))
            + """

No npm install needed for these modules:
"""
        )
        node_builtins = env.get("nodejs_builtins", {}).get("by_category", {})
        for category, modules in list(node_builtins.items())[
            :4
        ]:  # Show top 4 categories
            if isinstance(modules, list):
                md += f"\n**{category.replace('_', ' ').title()}:** {', '.join(modules[:15])}\n"

        md += """
## Bash Command Examples

### File Operations
"""
        file_ops = env.get("bash_commands", {}).get("file_operations", {})
        for cmd, info in list(file_ops.items())[:4]:  # Top 4 file commands
            examples = info.get("examples", [])
            if examples:
                md += f"\n**{cmd}:** `{examples[0]}`\n"

        md += "\n### Text Processing\n"
        text_ops = env.get("bash_commands", {}).get("text_processing", {})
        for cmd, info in list(text_ops.items())[:3]:  # Top 3 text commands
            examples = info.get("examples", [])
            if examples:
                md += f"**{cmd}:** `{examples[0]}`\n"

        md += """
## Environment Variables

Key variables available:
"""
        env_vars = env.get("environment_variables", {})
        for var, value in list(env_vars.items())[:10]:  # Top 10 vars
            # Truncate long paths
            display_value = value if len(value) < 50 else value[:47] + "..."
            md += f"- **{var}:** `{display_value}`\n"

        md += """
## Resource Limits
"""
        limits = env.get("resource_limits", {})
        if "disk" in limits:
            disk = limits["disk"]
            md += f"\n- **Disk Space:** {disk.get('available')} available ({disk.get('use_percent')} used)\n"
        md += f"- **Shared Memory:** {limits.get('shared_memory', 'unknown')}\n"

        md += """
---
*This context is auto-generated at sandbox startup and should not be manually edited.*
"""
        return md


def main():
    """Main entry point"""
    scanner = EnvironmentScanner(
        output_path=os.environ.get("SANDBOX_CONTEXT_JSON", "/app/sandbox_context.json")
    )

    # Scan environment
    scanner.scan_all()

    # Save both formats
    scanner.save_json()
    scanner.save_markdown(
        md_path=os.environ.get("SANDBOX_CONTEXT_MD", "/app/sandbox_context.md")
    )

    print("✓ Sandbox context generation complete", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
