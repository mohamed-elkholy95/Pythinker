# Sandbox Context Scripts

This directory contains scripts for generating and testing the sandbox environment context system.

## Scripts

### `generate_sandbox_context.py`

**Purpose:** Scans the sandbox environment and generates structured context files that agents can load to understand their capabilities without exploration.

**Runs:** Automatically at sandbox startup via supervisord (priority=5)

**Output Files:**
- `/app/sandbox_context.json` - Structured JSON for programmatic access
- `/app/sandbox_context.md` - Human-readable Markdown documentation

**Manual Execution:**
```bash
# Inside sandbox container
python3 /app/scripts/generate_sandbox_context.py

# From host (Docker)
docker exec -u ubuntu <sandbox-container> python3 /app/scripts/generate_sandbox_context.py
```

**What It Scans:**
- Operating system details (distribution, kernel, architecture)
- Python environment (version, 102+ packages, standard library modules)
- Node.js environment (version, global packages, built-in modules)
- System tools (git, curl, jq, ripgrep, etc.)
- Browser automation (Chromium, Playwright)
- Bash command patterns with flags and examples
- Execution patterns for Python, Node.js, Shell
- Environment variables
- File system structure and permissions
- Resource limits (disk, memory, CPU)
- Available services and ports

**Performance:** Completes in < 10 seconds

### `test_context_generation.py`

**Purpose:** Test suite for the original sandbox context system.

**Runs:** Manually for validation

**Tests:**
- Context generation
- JSON structure validation
- File creation
- Content verification

**Execution:**
```bash
docker exec -u ubuntu <sandbox-container> python3 /app/scripts/test_context_generation.py
```

### `test_enhanced_context.py`

**Purpose:** Comprehensive test suite for command reference enhancements.

**Runs:** Manually for validation of enhanced features

**Tests:**
- Bash command scanning
- Python stdlib detection
- Node.js builtin scanning
- Environment variable scanning
- Execution pattern generation
- Resource limit detection
- Full context generation
- JSON serialization
- Markdown generation

**Execution:**
```bash
# Inside sandbox
python3 /app/scripts/test_enhanced_context.py

# From host
docker exec -u ubuntu <sandbox-container> python3 /app/scripts/test_enhanced_context.py
```

**Expected Output:**
```
============================================================
Enhanced Sandbox Context Generation Tests
============================================================

Testing bash command scanning...
✓ Bash commands: 6 categories
Testing Python stdlib scanning...
✓ Python stdlib: 89 modules in 10 categories
Testing Node.js built-ins scanning...
✓ Node.js builtins: 30 modules in 6 categories
...
SUCCESS: All 9 tests passed!
```

### `example_sandbox_context.json`

**Purpose:** Example of generated context file structure.

**Use:** Reference for understanding the context file format.

## Integration

### Supervisord Configuration

The context generator runs automatically at startup:

```ini
[program:context_generator]
command=python3 /app/scripts/generate_sandbox_context.py
priority=5              # Runs before all other services
autorestart=false       # One-shot execution
stdout_logfile=/dev/stdout
stderr_logfile=/dev/stderr
```

See `sandbox/supervisord.conf` for full configuration.

### Backend Integration

The backend loads the generated context:

```python
from app.domain.services.prompts.sandbox_context import (
    SandboxContextManager,
    get_sandbox_context_prompt
)

# Load context (cached for 24 hours)
context = SandboxContextManager.load_context()

# Get prompt section for agents
prompt_section = get_sandbox_context_prompt()

# Get context statistics
stats = SandboxContextManager.get_context_stats()
```

See `backend/app/domain/services/prompts/sandbox_context.py` for full API.

### System Prompt Integration

Context is automatically injected into agent system prompts:

```python
from app.domain.services.prompts.system import build_system_prompt

# Context included by default
prompt = build_system_prompt()

# Optionally disable (not recommended)
prompt = build_system_prompt(include_sandbox_context=False)
```

See `backend/app/domain/services/prompts/system.py` for full API.

## Verification

### Check Context Generation

```bash
# View JSON context
docker exec <sandbox-container> cat /app/sandbox_context.json | jq '.'

# View markdown context
docker exec <sandbox-container> cat /app/sandbox_context.md

# Check specific sections
docker exec <sandbox-container> cat /app/sandbox_context.json | jq '.environment.bash_commands'
docker exec <sandbox-container> cat /app/sandbox_context.json | jq '.environment.python_stdlib.total_count'
docker exec <sandbox-container> cat /app/sandbox_context.json | jq '.environment.execution_patterns'
```

### Check Backend Loading

```python
from app.domain.services.prompts.sandbox_context import SandboxContextManager

# Check if context is available
stats = SandboxContextManager.get_context_stats()
print(f"Available: {stats['available']}")
print(f"Source: {stats['source']}")
print(f"Version: {stats['version']}")
print(f"Age: {stats['age_hours']} hours")

# Verify enhanced fields
context = SandboxContextManager.load_context()
env = context.get("environment", {})

print(f"\nEnhanced fields present:")
for field in ["bash_commands", "python_stdlib", "nodejs_builtins",
              "execution_patterns", "environment_variables", "resource_limits"]:
    print(f"  {field}: {bool(env.get(field))}")
```

### Check Agent Prompt

```python
from app.domain.services.prompts.system import build_system_prompt

prompt = build_system_prompt()

# Check for enhanced sections
checks = [
    "Python Standard Library",
    "Node.js Built-in Modules",
    "Common Command Patterns",
    "Bash Examples"
]

for check in checks:
    present = check in prompt
    print(f"{check}: {'✓' if present else '✗'}")
```

## Troubleshooting

### Issue: Context file not generated

**Check supervisord status:**
```bash
docker exec <container> supervisorctl status context_generator
```

**View logs:**
```bash
docker logs <container> 2>&1 | grep context_generator
```

**Run manually:**
```bash
docker exec -u ubuntu <container> python3 /app/scripts/generate_sandbox_context.py
```

### Issue: Context fields missing

**Validate JSON structure:**
```bash
docker exec <container> cat /app/sandbox_context.json | jq '.environment | keys'
```

**Expected keys:**
```json
[
  "bash_commands",
  "browser",
  "capabilities",
  "directories",
  "environment_variables",
  "execution_patterns",
  "nodejs",
  "nodejs_builtins",
  "os",
  "python",
  "python_stdlib",
  "resource_limits",
  "system_tools"
]
```

### Issue: Stale context

**Check context age:**
```python
from app.domain.services.prompts.sandbox_context import SandboxContextManager
stats = SandboxContextManager.get_context_stats()
print(f"Context age: {stats['age_hours']} hours")
```

**Force reload:**
```python
context = SandboxContextManager.load_context(force_reload=True)
```

**Regenerate:**
```bash
docker exec -u ubuntu <container> python3 /app/scripts/generate_sandbox_context.py
```

## Development

### Adding New Scanners

To add a new scanner method:

1. Add method to `EnvironmentScanner` class in `generate_sandbox_context.py`:
```python
def scan_your_feature(self) -> Dict[str, Any]:
    """Scan your feature"""
    return {
        "your_data": "value"
    }
```

2. Add to `scan_all()` method:
```python
self.context["environment"] = {
    # ... existing fields
    "your_feature": self.scan_your_feature(),
}
```

3. Add formatting method to `sandbox_context.py`:
```python
@classmethod
def _format_your_feature(cls, feature_data: Dict[str, Any]) -> str:
    """Format your feature for prompt"""
    return "- Formatted output"
```

4. Update `generate_prompt_section()` to include:
```python
your_feature=cls._format_your_feature(env.get("your_feature", {}))
```

5. Add test to `test_enhanced_context.py`:
```python
def test_your_feature():
    """Test your feature scanning"""
    scanner = EnvironmentScanner()
    data = scanner.scan_your_feature()
    assert "your_data" in data
```

### Testing Changes

```bash
# Syntax check
python3 -m py_compile sandbox/scripts/generate_sandbox_context.py

# Run tests
docker exec -u ubuntu <container> python3 /app/scripts/test_enhanced_context.py

# Generate and inspect
docker exec -u ubuntu <container> python3 /app/scripts/generate_sandbox_context.py
docker exec <container> cat /app/sandbox_context.json | jq '.environment.your_feature'
```

## Documentation

- **System Documentation:** `docs/SANDBOX_CONTEXT_SYSTEM.md`
- **Enhancement Documentation:** `docs/SANDBOX_CONTEXT_COMMAND_REFERENCE_ENHANCEMENT.md`
- **Implementation Report:** `CONTEXT_SYSTEM_IMPLEMENTATION_REPORT.md`
- **Migration Guide:** `MIGRATION_GUIDE_CONTEXT_SYSTEM.md`

## Performance

- **Generation time:** < 10 seconds
- **Context size:** 2-5 KB (JSON), 5-10 KB (Markdown)
- **Token cost:** ~800 tokens added to agent prompt (one-time per session)
- **Token savings:** 500-1500 tokens per session (elimination of exploration)
- **Net benefit:** 20-40% token reduction per session

## Version History

- **v1.0.0** - Initial sandbox context system
  - OS, Python, Node.js, tools, browser scanning
  - JSON and Markdown output
  - 24-hour caching
  - Automatic generation at startup

- **v1.1.0** - Command reference enhancement
  - Bash command examples with flags
  - Python standard library modules (89+)
  - Node.js built-in modules (30+)
  - Execution patterns (Python, Node.js, Shell)
  - Environment variables scanning
  - Resource limits detection
  - Enhanced prompts and documentation
