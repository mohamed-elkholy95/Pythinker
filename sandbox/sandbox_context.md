# Sandbox Environment Context

**Generated:** 2026-02-16T03:46:32.202545
**Version:** 1.0.0
**Checksum:** 355aa9edd4edf5c3

## Operating System

- **Distribution:** Ubuntu 22.04
- **Kernel:** 25.2.0
- **Architecture:** arm64
- **User:** panda
- **Home:** /Users/panda

## Python Environment

- **Version:** Python 3.9.6
- **Path:** /usr/bin/python3
- **Pip:** pip 21.2.4 from /Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/site-packages/pip (python 3.9)
- **Total Packages:** 33

### Key Python Packages

- **requests:** 2.32.5
- **numpy:** 2.0.2

## Node.js Environment

- **Version:** v24.12.0
- **NPM:** 11.6.2
- **PNPM:** 10.28.0
- **Yarn:** 1.22.22
- **Global Packages:** 9

## Browser Automation


## System Tools

### Development Tools
- **git:** git version 2.52.0
- **gcc:** Apple clang version 17.0.0 (clang-1700.6.3.2)
- **make:** GNU Make 3.81
- **gh:** gh version 2.83.2 (2025-12-10)

### Text Processing
- grep
- sed
- awk
- jq

### Network Tools
- curl
- wget
- netstat
- ping
- nc

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
- **PATH:** `/Users/panda/.codex/tmp/arg0/codex-arg03sUFDt:/...`
- **HOME:** `/Users/panda`
- **USER:** `panda`
- **SHELL:** `/bin/zsh`
- **TERM:** `xterm-256color`
- **LANG:** `C.UTF-8`
- **LC_ALL:** `C.UTF-8`
- **NVM_DIR:** `/Users/panda/.nvm`

## Resource Limits
- **Shared Memory:** 2gb

---
*This context is auto-generated at sandbox startup and should not be manually edited.*
