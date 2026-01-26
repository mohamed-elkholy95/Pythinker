# Comprehensive Sandbox Environment Report

**Author:** Manus AI
**Date:** January 26, 2026

## 1. Introduction

This report provides a comprehensive, detailed account of the sandbox environment, including the operating system configuration, loaded environment variables, installed applications, and a log of executed diagnostic commands and their outcomes. The objective is to fully document the capabilities and current state of the execution environment.

## 2. System Overview and Resources

The sandbox operates on a Linux-based system, specifically **Ubuntu 22.04.5 LTS (Jammy Jellyfish)**. The environment is configured with a standard user account (`ubuntu`) and is running on an `x86_64` architecture.

| Metric | Value | Source Command |
| :--- | :--- | :--- |
| Operating System | Ubuntu 22.04.5 LTS | `cat /etc/os-release` |
| Architecture | x86_64 | `uname -a` |
| Uptime | 4 days, 6 hours, 24 minutes | `uptime` |
| Total Memory (RAM) | 3941 MB | `free -m` |
| Used Memory (RAM) | 856 MB | `free -m` |
| Filesystem Size | 42 GB | `df -h` |
| Filesystem Used | 9.8 GB (24%) | `df -h` |
| Timezone | America/New_York (EST) | `env` |

## 3. Environment Variables

The environment is configured with numerous variables, including standard system paths and specialized variables for service integration and configuration. **Security-sensitive variables (e.g., API keys, passwords) have been redacted.**

| Variable | Value (Redacted/Sample) | Description |
| :--- | :--- | :--- |
| `PATH` | .../pnpm:/.../node/v22.13.0/bin:/usr/local/bin:... | Defines the directories searched for executable commands. |
| `HOME` | /home/ubuntu | The home directory for the `ubuntu` user. |
| `SHELL` | /bin/bash | The default command interpreter. |
| `TZ` | America/New_York | The system timezone setting. |
| `OPENAI_API_KEY` | `sk-REDACTED` | API key for accessing the OpenAI-compatible LLM proxy. |
| `OPENAI_API_BASE` | `https://api.manus.im/api/llm-proxy/v1` | The base URL for the LLM proxy service. |
| `RUNTIME_API_HOST` | `https://api.manus.im` | The host for the runtime API services. |
| `NVM_DIR` | /home/ubuntu/.nvm | Node Version Manager directory. |
| `PNPM_HOME` | /home/ubuntu/.local/share/pnpm | pnpm package manager home directory. |
| `SUDO_USER` | ubuntu | The user who invoked the current shell via `sudo`. |

## 4. Installed Software Inventory

The sandbox is equipped with a comprehensive set of tools and programming environments, installed via the Debian package manager (`dpkg`), Python's `pip`, and Node.js package managers (`npm`/`pnpm`).

### 4.1 Core System Utilities and Command-Line Tools

The environment includes essential development and utility tools:

| Tool | Version | Package Manager |
| :--- | :--- | :--- |
| **Python** | 3.11.0rc1 | System/Source |
| **Node.js** | v22.13.0 | NVM |
| **Git** | 2.34.1 | dpkg |
| **GitHub CLI (`gh`)** | 2.81.0 | dpkg |
| **bc** | 1.07.1 | dpkg |
| **curl** | 7.81.0 | dpkg |
| **unzip/zip** | 6.0 | dpkg |
| **tar** | 1.34 | dpkg |
| **ffmpeg** | 4.4.2 | dpkg |
| **Chromium** | 1:128.0.6613.137 | dpkg |
| **code-server** | 4.104.3 | dpkg |

### 4.2 Python Packages (pip)

The Python environment is rich with packages for data science, web development, and document processing:

| Category | Key Packages |
| :--- | :--- |
| **Data Science/Analysis** | `numpy`, `pandas`, `matplotlib`, `seaborn`, `plotly`, `jmespath` |
| **Web/API Development** | `fastapi`, `flask`, `uvicorn`, `starlette`, `requests`, `httpx`, `anyio` |
| **Web Scraping/Parsing** | `beautifulsoup4`, `lxml`, `cssselect2`, `playwright` |
| **Document/Media Processing** | `fpdf2`, `reportlab`, `xhtml2pdf`, `weasyprint`, `pdf2image`, `pillow`, `markdown` |
| **Cloud/AWS** | `boto3`, `botocore`, `s3transfer` |

### 4.3 Node.js Packages (pnpm/npm)

The Node.js environment is configured with `nvm` and includes global packages for development and utility:

| Package | Version | Manager |
| :--- | :--- | :--- |
| **Node.js** | v22.13.0 | NVM |
| **pnpm** | 10.28.1 | npm |
| **yarn** | 1.22.22 | pnpm (global) |
| **@anthropic-ai/mcpb** | 2.1.2 | pnpm (global) |
| **@mermaid-js/mermaid-cli** | 11.12.0 | pnpm (global) |

### 4.4 Specialized Manus Utility Commands

The sandbox provides a set of specialized command-line utilities for common AI-related tasks:

| Command | Description | Example Usage |
| :--- | :--- | :--- |
| `manus-mcp-cli` | Comprehensive CLI for interacting with Model Context Protocol (MCP) servers. | `manus-mcp-cli auth` |
| `manus-render-diagram` | Renders diagram files (.mmd, .d2, .puml, .md) to PNG format. | `manus-render-diagram diagram.mmd output.png` |
| `manus-md-to-pdf` | Converts a Markdown file to PDF format. | `manus-md-to-pdf input.md output.pdf` |
| `manus-speech-to-text` | Transcribes speech/audio/video files to text. | `manus-speech-to-text audio.mp3` |
| `manus-upload-file` | Uploads a file to S3 to obtain a direct public URL. | `manus-upload-file image.png` |
| `manus-export-slides` | Exports slides from a `manus-slides://` URI to PDF or PPT format. | `manus-export-slides manus-slides://{id} pdf` |

## 5. Command Execution Log

The following table summarizes the execution of key diagnostic commands, documenting the system's operational status and software versions.

| Command | Purpose | Key Output/Result |
| :--- | :--- | :--- |
| `uptime` | System load and uptime | `up 4 days, 6:24, load average: 0.76, 0.95, 0.98` |
| `df -h` | Disk space usage | `/dev/root 42G (24% used)` |
| `free -m` | Memory usage | `Mem: 3941 total, 856 used` |
| `gh --version` | GitHub CLI version | `gh version 2.81.0` |
| `git --version` | Git version | `git version 2.34.1` |
| `python3 --version` | Python version | `Python 3.11.0rc1` |
| `node --version` | Node.js version | `v22.13.0` |
| `manus-mcp-cli --help` | MCP CLI functionality | Commands include `auth`, `prompt`, `resource`, `tool`. |
| `manus-render-diagram --help` | Diagram rendering utility | Supports `.mmd`, `.d2`, `.puml` to PNG. |
| `manus-speech-to-text --help` | Transcription utility | Transcribes audio/video files. |

## 6. Conclusion

The sandbox environment is a robust, well-equipped Linux system running Ubuntu 22.04. It features up-to-date programming environments for Python (3.11) and Node.js (22.13), alongside a comprehensive suite of development tools like Git and GitHub CLI. The presence of specialized `manus` utilities for diagram rendering, document conversion, transcription, and cloud file handling significantly extends the environment's capabilities for complex, multi-modal tasks. The environment is stable, with a low load average and ample available memory and disk space.
