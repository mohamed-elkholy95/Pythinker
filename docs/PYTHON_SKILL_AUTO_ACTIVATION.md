# Python Skill Auto-Activation Hook

## Overview

A PreToolUse hook that automatically detects Python/backend code operations and recommends the appropriate Python development agent or skill. This ensures Claude Code consistently uses expert-level Python capabilities when working on backend code.

## How It Works

### 1. Hook Triggers
The hook (`~/.claude/hooks/python_skill_activator.py`) monitors these operations:
- **Edit**: File content modifications
- **Write**: New file creation
- **MultiEdit**: Multiple file edits
- **Bash**: Command execution (detects Python-related commands)
- **Read**: File reading (for context)

### 2. Context Detection
The hook analyzes:
- **File path patterns**: `backend/app/domain`, `backend/app/interfaces/api`, `backend/tests`, etc.
- **File extensions**: `.py`, `requirements*.txt`, `pyproject.toml`
- **Content patterns**: FastAPI imports, pytest fixtures, async/await, Pydantic models
- **Bash commands**: `python`, `pytest`, `ruff`, `uvicorn`, `conda`

### 3. Agent/Skill Recommendation
Based on context, recommends:

#### Pro Agents (Comprehensive Experts - Use Opus Model)
- **python-development:fastapi-pro** - FastAPI/API development
  - Triggered by: `backend/app/interfaces/api/*`, FastAPI imports, APIRouter
  - Expertise: Async APIs, SQLAlchemy 2.0, Pydantic V2, microservices

- **python-development:python-pro** - General Python development
  - Triggered by: `backend/app/domain/*`, `backend/app/infrastructure/*`, generic Python
  - Expertise: Python 3.12+, modern tooling (uv, ruff), async patterns, production practices

- **python-development:django-pro** - Django development
  - Expertise: Django 5.x, ORM, DRF, Celery, Django Channels

#### Skills (Focused Knowledge Modules)
- **python-development:python-testing-patterns** - Test implementation
  - Triggered by: `backend/tests/*`, pytest patterns

- **python-development:async-python-patterns** - Async programming
  - Triggered by: `async def`, `asyncio`, `aiohttp`

- **python-development:python-configuration** - Configuration management
  - Triggered by: `backend/app/core/config.py`

- **python-development:python-packaging** - Dependencies
  - Triggered by: `requirements*.txt`, `pyproject.toml`, `setup.py`

### 4. Recommendation Display
When triggered, shows formatted message:

```
╔════════════════════════════════════════════════════════════════╗
║  🤖 PRO AGENT ACTIVATION RECOMMENDED                    ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Context: FastAPI endpoint development                         ║
║  File: routes.py                                                ║
║                                                                ║
║  Recommended: python-development:fastapi-pro                   ║
║  FastAPI Expert • Async APIs • SQLAlchemy 2.0 • Pydantic V2 • Microservices║
║                                                                ║
║  Pro agents use Opus for comprehensive expertise                ║
║                                                                ║
║  To use: Skill tool will invoke automatically on next action   ║
║  To disable hook: export ENABLE_PYTHON_SKILL_HOOK=0            ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

## Usage

### For Claude Code (AI Agent)

**CRITICAL**: When you see a hook recommendation message, **immediately invoke the recommended agent** using the Skill tool:

```
# Invoke agent with no arguments
Skill tool: python-development:fastapi-pro

# Or invoke agent with specific task
Skill tool: python-development:fastapi-pro
Arguments: "Implement async endpoint with proper error handling"
```

**Do NOT**:
- ❌ Ignore the recommendation
- ❌ Proceed without invoking the skill
- ❌ Use generic capabilities instead of specialized agents

**DO**:
- ✅ Immediately invoke the recommended agent/skill
- ✅ Let the specialized agent handle the work
- ✅ Trust the agent's comprehensive expertise

### For Users

The hook runs automatically - no action needed. Messages appear in Claude Code's conversation.

**To disable temporarily:**
```bash
export ENABLE_PYTHON_SKILL_HOOK=0
```

**To re-enable:**
```bash
unset ENABLE_PYTHON_SKILL_HOOK
```

## Hook Architecture

### Files
```
~/.claude/hooks/
├── python_skill_activator.py  # Hook script (executable)
└── hooks.json                 # Hook configuration
```

### State Management
- **Session-scoped**: Recommendations shown once per file/agent per session
- **State file**: `~/.claude/python_skill_activations_{session_id}.json`
- **Tracks**: Which agents have been recommended for which files
- **Auto-cleanup**: Session state is ephemeral

### Debug Logging
Hook logs to `/tmp/python-skill-hook-log.txt`:
```bash
tail -f /tmp/python-skill-hook-log.txt
```

## Installation

The hook is already installed at:
- Script: `~/.claude/hooks/python_skill_activator.py`
- Config: `~/.claude/hooks/hooks.json`

To reinstall or update:

```bash
# Ensure script is executable
chmod +x ~/.claude/hooks/python_skill_activator.py

# Test hook manually
echo '{"session_id": "test", "tool_name": "Edit", "tool_input": {"file_path": "backend/app/interfaces/api/routes.py", "new_string": "from fastapi import APIRouter"}}' | python3 ~/.claude/hooks/python_skill_activator.py
```

## Configuration

### Hooks.json
```json
{
  "description": "Pythinker repository hooks for automatic Python skill activation",
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/panda/.claude/hooks/python_skill_activator.py"
          }
        ],
        "matcher": "Edit|Write|MultiEdit|Bash|Read",
        "description": "Activate Python development skills when working on Python/backend code"
      }
    ]
  }
}
```

### Customization

Edit `python_skill_activator.py` to adjust:

**File Patterns** (`should_activate_skill` function):
```python
python_patterns = {
    "backend/app/interfaces/api": ("python-development:fastapi-pro", "FastAPI endpoint development", "agent"),
    "backend/app/domain": ("python-development:python-pro", "Domain model implementation", "agent"),
    # Add more patterns...
}
```

**Content Detection**:
```python
# FastAPI patterns
if any(kw in content for kw in ["fastapi", "APIRouter", "@app.", "HTTPException"]):
    return True, "python-development:fastapi-pro", "FastAPI code patterns detected", "agent"
```

## Decision Matrix

| File Path | Content | Recommended | Type |
|-----------|---------|-------------|------|
| `backend/app/interfaces/api/*` | Any | fastapi-pro | Agent |
| `backend/app/domain/*` | Any | python-pro | Agent |
| `backend/app/infrastructure/*` | Any | python-pro | Agent |
| `backend/tests/*` | Any | python-testing-patterns | Skill |
| `backend/app/core/config.py` | Any | python-configuration | Skill |
| `backend/**/*.py` | `fastapi`, `APIRouter` | fastapi-pro | Agent |
| `backend/**/*.py` | `pytest`, `def test_` | python-testing-patterns | Skill |
| `backend/**/*.py` | `async def`, `asyncio` | async-python-patterns | Skill |
| `backend/**/*.py` | `BaseModel`, `Field(` | python-pro | Agent |
| `requirements*.txt`, `pyproject.toml` | Any | python-packaging | Skill |
| Bash command | `python`, `pytest`, `ruff` | python-pro | Agent |

## Benefits

1. **Consistent Expertise**: Ensures specialized Python knowledge is always used
2. **Automatic Detection**: No manual skill invocation needed
3. **Context-Aware**: Recommends the right agent/skill for each situation
4. **Non-Blocking**: Shows recommendation but allows work to continue
5. **Session-Scoped**: Avoids repetitive recommendations
6. **Comprehensive**: Covers API development, testing, async patterns, configuration, etc.

## Pro Agents vs Skills

### Pro Agents (Comprehensive)
- Use **Opus model** for maximum capability
- Comprehensive domain expertise
- Suitable for complex, multi-step work
- Examples: fastapi-pro, python-pro, django-pro

### Skills (Focused)
- Focused knowledge modules
- Specific topic expertise
- Suitable for targeted tasks
- Examples: python-testing-patterns, async-python-patterns

## Troubleshooting

### Hook Not Triggering
```bash
# Check hook is installed
ls -la ~/.claude/hooks/python_skill_activator.py

# Verify executable permission
chmod +x ~/.claude/hooks/python_skill_activator.py

# Test manually
echo '{"session_id": "test", "tool_name": "Edit", "tool_input": {"file_path": "backend/test.py", "new_string": "print()"}}' | python3 ~/.claude/hooks/python_skill_activator.py
```

### Check Debug Logs
```bash
tail -20 /tmp/python-skill-hook-log.txt
```

### Verify hooks.json
```bash
cat ~/.claude/hooks/hooks.json
python3 -m json.tool ~/.claude/hooks/hooks.json
```

### Hook Disabled
```bash
# Check environment variable
echo $ENABLE_PYTHON_SKILL_HOOK

# Re-enable if disabled
unset ENABLE_PYTHON_SKILL_HOOK
```

## Related Documentation

- **CLAUDE.md**: Project guidelines and automatic activation workflow
- **MEMORY.md**: Critical action required when hook messages appear
- **instructions.md**: Core engineering behaviors
- **Python Standards**: `docs/guides/PYTHON_STANDARDS.md`

## Change Log

### 2026-02-16 - Initial Release
- Created PreToolUse hook for Python skill auto-activation
- Supports FastAPI, general Python, testing, async, config patterns
- Session-scoped recommendations
- Comprehensive agent/skill mapping
- Updated CLAUDE.md and MEMORY.md with workflow documentation
