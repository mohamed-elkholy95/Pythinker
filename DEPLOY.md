# 🚀 Deployment Instructions - Sandbox Context System

## Quick Start

```bash
# 1. Rebuild sandbox image
./build.sh

# 2. Restart development stack
./dev.sh down
./dev.sh up -d

# 3. Watch context generation
./dev.sh logs -f sandbox | grep -A 5 context_generator
```

**Expected Output:**
```
[context_generator] Scanning sandbox environment...
[context_generator] Environment scan complete!
[context_generator] Context saved to /app/sandbox_context.json
[context_generator] Markdown context saved to /app/sandbox_context.md
[context_generator] ✓ Sandbox context generation complete
[context_generator] exited: context_generator (exit status 0; expected)
```

---

## Verification Steps

### Step 1: Verify Context Files Generated

```bash
docker exec pythinker-sandbox-1 ls -lh /app/sandbox_context.*
```

**Expected:**
```
-rw-r--r-- 1 ubuntu ubuntu 8.7K /app/sandbox_context.json
-rw-r--r-- 1 ubuntu ubuntu 2.6K /app/sandbox_context.md
```

### Step 2: Check Context Metadata

```bash
docker exec pythinker-sandbox-1 cat /app/sandbox_context.json | \
  python3 -c 'import json, sys; d=json.load(sys.stdin); print(f"Version: {d[\"version\"]}\nPackages: Python={d[\"environment\"][\"python\"][\"package_count\"]}, Node={d[\"environment\"][\"nodejs\"][\"package_count\"]}")'
```

**Expected:**
```
Version: 1.0.0
Packages: Python=102, Node=10
```

### Step 3: Test Backend Integration

```bash
# Copy context to backend
docker exec pythinker-sandbox-1 cat /app/sandbox_context.json | \
  docker exec -i pythinker-backend-1 tee /app/sandbox_context.json > /dev/null

# Test loading
docker exec pythinker-backend-1 python3 << 'EOF'
from app.domain.services.prompts.sandbox_context import SandboxContextManager
stats = SandboxContextManager.get_context_stats()
print(f"✓ Context available: {stats['available']}")
print(f"✓ Version: {stats.get('version', 'N/A')}")
print(f"✓ Python packages: {stats.get('package_counts', {}).get('python', 0)}")
EOF
```

**Expected:**
```
✓ Context available: True
✓ Version: 1.0.0
✓ Python packages: 102
```

### Step 4: Verify System Prompt Integration

```bash
docker exec pythinker-backend-1 python3 << 'EOF'
from app.domain.services.prompts.system import build_system_prompt

prompt = build_system_prompt()
has_context = "sandbox_environment_knowledge" in prompt.lower()
print(f"✓ System prompt includes context: {has_context}")
print(f"✓ Prompt length: {len(prompt)} characters")
EOF
```

**Expected:**
```
✓ System prompt includes context: True
✓ Prompt length: 5000-8000 characters
```

### Step 5: Test Agent Behavior

**Create a test session and monitor tool calls:**

```python
import requests

# Create session
response = requests.put("http://localhost:8000/api/v1/sessions", json={
    "workflow": "planact"
})
session_id = response.json()["session_id"]

# Send task
response = requests.post(
    f"http://localhost:8000/api/v1/sessions/{session_id}/chat",
    json={"message": "Write a Python script to calculate fibonacci numbers"},
    stream=True
)

# Monitor tool calls
for line in response.iter_lines():
    if line:
        print(line.decode())
```

**Verify:**
- ❌ NO commands like: `python3 --version`, `pip list`, `which git`
- ✅ Direct actions: `file_write(...)`, `shell_exec("python3 script.py")`

---

## Rollback Procedure

If issues occur, quick rollback options:

### Option 1: Disable Context in Prompts (Quickest)

```bash
# Edit system.py to disable context
docker exec pythinker-backend-1 bash -c 'cat > /tmp/disable_context.py << EOF
import sys
sys.path.insert(0, "/app")
from app.domain.services.prompts import system
# Monkey patch to disable
original_build = system.build_system_prompt
def patched_build(*args, **kwargs):
    kwargs["include_sandbox_context"] = False
    return original_build(*args, **kwargs)
system.build_system_prompt = patched_build
EOF'

# Restart backend
docker restart pythinker-backend-1
```

### Option 2: Remove Context Generator (Clean)

```bash
# Edit supervisord.conf to comment out context_generator
docker exec pythinker-sandbox-1 supervisorctl stop context_generator
docker exec pythinker-sandbox-1 rm -f /app/sandbox_context.*

# Restart sandbox
docker restart pythinker-sandbox-1
```

### Option 3: Full Revert

```bash
# Revert git changes
git checkout sandbox/supervisord.conf
git checkout backend/app/domain/services/prompts/system.py

# Rebuild
./build.sh
./dev.sh down && ./dev.sh up -d
```

---

## Monitoring

### Health Check Endpoint (Optional - Add Later)

```python
# Add to backend/app/interfaces/api/routes/health.py
from app.domain.services.prompts.sandbox_context import SandboxContextManager

@router.get("/context/stats")
async def context_stats():
    return SandboxContextManager.get_context_stats()
```

### Logs to Monitor

```bash
# Context generation
./dev.sh logs sandbox | grep context

# Backend context loading
./dev.sh logs backend | grep -i "sandbox context"

# Agent behavior (should see no exploratory commands)
./dev.sh logs backend | grep -i "shell_exec.*version"
```

---

## Success Metrics

Track these metrics before/after:

1. **Token Usage**
   - Average tokens per session
   - Target: 20-40% reduction

2. **Latency**
   - Time from user message to first tool call
   - Target: 50-80% reduction

3. **Exploratory Commands**
   - Count of `shell_exec` with version/which/list commands
   - Target: Zero

4. **Error Rate**
   - Overall error rate should remain stable
   - Target: No increase

---

## Troubleshooting

### Context not generated

```bash
# Check supervisord status
docker exec pythinker-sandbox-1 supervisorctl status context_generator

# Check logs
docker exec pythinker-sandbox-1 supervisorctl tail -f context_generator stderr

# Manually run
docker exec pythinker-sandbox-1 python3 /app/scripts/generate_sandbox_context.py
```

### Backend can't load context

```bash
# Check file exists and permissions
docker exec pythinker-backend-1 ls -l /app/sandbox_context.json

# Copy from sandbox if needed
docker exec pythinker-sandbox-1 cat /app/sandbox_context.json | \
  docker exec -i pythinker-backend-1 tee /app/sandbox_context.json > /dev/null
```

### Agents still using exploratory commands

```bash
# Verify system prompt includes context
docker exec pythinker-backend-1 python3 -c "
from app.domain.services.prompts.system import build_system_prompt
print('sandbox_environment_knowledge' in build_system_prompt().lower())
"

# Should print: True
```

---

## Production Deployment

After successful dev/staging validation:

```bash
# 1. Build production images
./build.sh

# 2. Deploy during low-traffic window
./run.sh down
./run.sh up -d

# 3. Monitor startup
./run.sh logs -f sandbox | grep context

# 4. Verify health
curl http://your-domain/health

# 5. Monitor metrics for 24-48 hours
./run.sh logs backend | grep -i error
```

---

## Documentation Reference

- **Full System Guide:** `docs/SANDBOX_CONTEXT_SYSTEM.md`
- **Migration Guide:** `MIGRATION_GUIDE_CONTEXT_SYSTEM.md`
- **Implementation Report:** `CONTEXT_SYSTEM_IMPLEMENTATION_REPORT.md`
- **Success Report:** `IMPLEMENTATION_SUCCESS.md`

---

## Support

For issues:
1. Check documentation above
2. Review logs: `./dev.sh logs -f sandbox backend`
3. Run validation: `./validate_context_system.sh`
4. File GitHub issue with logs

---

**Status:** ✅ Ready for deployment
**Next Action:** Run `./build.sh` to rebuild with context system integrated
