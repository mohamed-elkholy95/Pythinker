# Sandbox Environment Context

**Generated:** 2026-02-17T23:30:35.680379
**Version:** 1.0.0
**Checksum:** 4d1f019f78f35f2d

## Operating System

- **Distribution:** Ubuntu 22.04
- **Kernel:** 6.12.67-linuxkit
- **Architecture:** aarch64
- **User:** ubuntu
- **Home:** /home/ubuntu

## Python Environment

- **Version:** Python 3.11.14
- **Path:** /opt/base-python-venv/bin/python3
- **Pip:** pip 26.0.1 from /opt/base-python-venv/lib/python3.11/site-packages/pip (python 3.11)
- **Total Packages:** 123

### Key Python Packages

- **fastapi:** 0.119.0
- **uvicorn:** 0.37.0
- **pydantic:** 2.12.1
- **playwright:** 1.55.0
- **pytest:** 9.0.2
- **requests:** 2.32.5
- **httpx:** 0.28.1
- **aiohttp:** 3.13.3
- **pandas:** 2.3.3
- **numpy:** 2.3.3

## Node.js Environment

- **Version:** v22.13.0
- **NPM:** 10.9.2
- **PNPM:** 10.29.2
- **Yarn:** None
- **Global Packages:** 8

## Browser Automation

- **Chrome for Testing:** Chromium 140.0.7339.16
- **Playwright:** Available (browsers: chromium, firefox, webkit)
- **Stealth Mode:** No

## System Tools

### Development Tools
- **git:** git version 2.34.1

### Text Processing
- grep
- sed
- awk
- jq

### Network Tools
- curl
- wget

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
- **/workspace:** User code execution workspace (RW)
- **/home/ubuntu:** Default user home directory (RW)
- **/app:** Sandbox service application (RW)
- **/tmp:** Temporary files (RW)

## Execution Patterns

### Python Execution
- **Run Script:** `python3 script.py`
- **Run Module:** `python3 -m module_name`
- **Run With Args:** `python3 script.py arg1 arg2`
- **Pip Install:** `pip3 install package_name`
- **Pip Install Requirements:** `pip3 install -r requirements.txt`
- **Run Tests:** `pytest tests/`
- **Run Single Test:** `pytest tests/test_file.py::test_function`
- **Check Syntax:** `python3 -m py_compile script.py`
- **Format Code:** `black script.py`
- **Type Check:** `mypy script.py`

### Node.js Execution
- **Run Script:** `node script.js`
- **Run With Esm:** `node --input-type=module script.mjs`
- **Npm Install:** `npm install package_name`
- **Npm Install Dev:** `npm install --save-dev package_name`
- **Npm Install Deps:** `npm install`
- **Pnpm Install:** `pnpm add package_name`
- **Run Tests:** `npm test`
- **Run Jest:** `jest tests/`
- **Check Syntax:** `node --check script.js`
- **Format Code:** `prettier --write script.js`
- **Type Check:** `tsc --noEmit`

### Shell Patterns
- **Make Executable:** `chmod +x script.sh`
- **Run Background:** `nohup command &`
- **Run With Timeout:** `timeout 30s command`
- **Redirect Output:** `command > output.txt 2>&1`
- **Pipe Commands:** `command1 | command2 | command3`
- **Run In Subshell:** `(cd /path && command)`
- **Check Exit Code:** `command && echo 'success' || echo 'failed'`

## Python Standard Library

**Total Built-in Modules:** 74

No pip install needed for these modules:

**Core:** os, sys, re, json, datetime, time, math, random, collections, itertools

**File Io:** pathlib, shutil, tempfile, glob, fnmatch, io, csv

**Data:** pickle, shelve, sqlite3, hashlib, hmac, secrets, uuid

**Text:** string, textwrap, difflib, unicodedata

**Network:** http.client, urllib.request, urllib.parse, socket, ssl, email, smtplib, ftplib

## Node.js Built-in Modules

**Total Built-in Modules:** 31

No npm install needed for these modules:

**Core:** assert, buffer, child_process, cluster, crypto, dgram, dns, domain, events, fs, http, http2, https, net, os

**File System:** fs, fs/promises, path

**Network:** http, https, http2, net, dgram, dns, tls

**Streams:** stream, stream/promises, stream/web

## Bash Command Examples

### File Operations

**ls:** `ls -la`

**cat:** `cat file.txt`

**grep:** `grep -rn 'pattern' .`

**find:** `find . -name '*.py'`

### Text Processing
**jq:** `jq '.' file.json`
**sort:** `sort file.txt`
**uniq:** `sort file.txt | uniq`

## Environment Variables

Key variables available:
- **PATH:** `/opt/base-python-venv/bin:/home/ubuntu/.local/s...`
- **HOME:** `/home/ubuntu`
- **NODE_VERSION:** `22.13.0`
- **NVM_DIR:** `/usr/local/nvm`
- **VIRTUAL_ENV:** `/opt/base-python-venv`
- **PNPM_HOME:** `/home/ubuntu/.local/share/pnpm`

## Resource Limits

- **Disk Space:** 13G available (84% used)
- **Shared Memory:** 2gb

---
*This context is auto-generated at sandbox startup and should not be manually edited.*
