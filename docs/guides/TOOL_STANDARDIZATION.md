# Tool Display Standardization Guide

## Overview

This document defines the standardized display format for all tool operations in Pythinker, following Pythinker AI's design patterns.

## Display Format

All tool operations follow this unified format:

```
[icon] Verb Resource
```

**Examples:**
- `[🔍] Searching https://openrouter.ai/pricing`
- `[📄] Reading /workspace/config.json`
- `[🖥️] Running npm install`
- `[✏️] Editing src/components/App.vue`
- `[🌐] Browsing https://github.com`

## Standardized Tool Verbs

### Search Operations
| Function | Verb | Resource Display |
|----------|------|------------------|
| `web_search` | Searching | query string |
| `wide_research` | Searching | topic |
| `search` | Searching | URL or query |

### File Operations
| Function | Verb | Resource Display |
|----------|------|------------------|
| `file_read` | Reading | file path |
| `file_write` | Creating | file path |
| `file_str_replace` | Editing | file path |
| `file_find_in_content` | Searching | file path |
| `file_find_by_name` | Finding | directory path |

### Shell Operations
| Function | Verb | Resource Display |
|----------|------|------------------|
| `shell_exec` | Running | command (truncated) |
| `shell_view` | Viewing | shell session |
| `shell_wait` | Waiting | shell session |
| `shell_kill_process` | Stopping | process |

### Browser Operations
| Function | Verb | Resource Display |
|----------|------|------------------|
| `browser_navigate` | Browsing | URL |
| `browser_view` | Viewing | page |
| `browser_click` | Clicking | element |
| `browser_input` | Typing | text (truncated) |
| `browser_scroll_*` | Scrolling | direction |
| `browser_get_content` | Fetching | URL |

### Code Execution
| Function | Verb | Resource Display |
|----------|------|------------------|
| `code_execute` | Executing | language |
| `code_execute_python` | Running | Python code |
| `code_execute_javascript` | Running | JavaScript code |

### Communication
| Function | Verb | Resource Display |
|----------|------|------------------|
| `message_notify_user` | Notifying | (none) |
| `message_ask_user` | Asking | question (truncated) |

### Browser Agent (Autonomous)
| Function | Verb | Resource Display |
|----------|------|------------------|
| `browser_agent_run` | Browsing | task description |
| `browser_agent_extract` | Extracting | extraction goal |
| `go_to_url` | Opening | URL |
| `click_element` | Clicking | element |
| `input_text` | Typing | text |
| `extract_content` | Reading | page |

### Other
| Function | Verb | Resource Display |
|----------|------|------------------|
| `idle_standby` | Standing by | reason |
| `skill_invoke` | Loading | skill name |

## Icon Mapping

| Tool Category | Icon | Vue Component |
|---------------|------|---------------|
| Search | 🔍 | `SearchIcon` |
| File/Editor | ✏️ | `EditIcon` |
| Shell/Terminal | 🖥️ | `ShellIcon` |
| Browser | 🌐 | `BrowserIcon` |
| Web Pilot | 🌍 | `GlobeIcon` |
| Code Executor | 🐍 | `PythonIcon` |
| Idle | ⏸️ | `IdleIcon` |
| Agent Mode | 🤖 | `AgentModeIcon` |

## Implementation Rules

### 1. Resource Truncation
- URLs: Show domain + path (max 50 chars)
- Commands: Show first 40 chars + "..."
- Queries: Show in quotes, max 50 chars
- File paths: Remove `/home/ubuntu/` prefix

### 2. Verb Consistency
- Always use present continuous tense (-ing)
- Capitalize first letter only
- Keep verbs short (1-2 words max)

### 3. Activity Bar Format
```
[icon] Pythinker is using [Tool Name] | [Verb] [Resource]
```

**Example:**
```
[🔍] Pythinker is using Search | Searching "OpenRouter pricing 2026"
```

### 4. Content Header Format
```
[Tool Category]
```

**Examples:**
- `Search` (for all search operations)
- `Terminal` (for all shell operations)
- `Browser` (for all browser operations)
- `Editor` (for all file operations)

## Unified Tool Categories

To reduce confusion, multiple similar tools are consolidated under unified categories:

| Category | Includes | Display Name |
|----------|----------|--------------|
| Search | `search`, `info`, `web_search`, `wide_research` | Search |
| Terminal | `shell`, `code_executor` | Terminal |
| Browser | `browser`, `browser_agent`, `browsing` | Browser |
| Editor | `file` | Editor |
