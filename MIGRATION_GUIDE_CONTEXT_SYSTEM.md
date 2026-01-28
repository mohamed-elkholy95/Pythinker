# Migration Guide: Sandbox Context System

## Overview

This guide helps you deploy and validate the new Sandbox Environment Context System.

**Objective:** Eliminate token waste from exploratory commands by pre-loading environment knowledge into agents.

---

## Prerequisites

- Docker and Docker Compose installed
- Access to rebuild sandbox image
- Basic understanding of Pythinker architecture

---

## Migration Steps

### Step 1: Update Codebase

The following files have been created/modified:

**New Files:**
```
✓ sandbox/scripts/generate_sandbox_context.py
✓ sandbox/scripts/test_context_generation.py
✓ sandbox/scripts/example_sandbox_context.json
✓ sandbox/scripts/README.md
✓ backend/app/domain/services/prompts/sandbox_context.py
✓ docs/SANDBOX_CONTEXT_SYSTEM.md
```

**Modified Files:**
```
✓ sandbox/supervisord.conf
✓ backend/app/domain/services/prompts/system.py
```

**Verification:**

```bash
# Check all files exist
ls -l sandbox/scripts/generate_sandbox_context.py
ls -l backend/app/domain/services/prompts/sandbox_context.py
ls -l docs/SANDBOX_CONTEXT_SYSTEM.md

# Verify scripts are executable
chmod +x sandbox/scripts/generate_sandbox_context.py
chmod +x sandbox/scripts/test_context_generation.py
```

---

### Step 2: Rebuild Sandbox Image

The context generation script needs to be included in the sandbox image.

**Build:**

```bash
# Development build
./dev.sh build

# Production build
./build.sh
```

**Verification:**

```bash
# Check image contains scripts
docker run --rm pythinker-sandbox:latest ls -l /app/scripts/

# Expected output:
# generate_sandbox_context.py
# test_context_generation.py
# example_sandbox_context.json
# README.md
```

---

### Step 3: Test Context Generation

Before deploying, test the context generation in isolation.

**Run Test Container:**

```bash
# Start a test sandbox
docker run -it --rm pythinker-sandbox:latest bash

# Inside container, run generator
python3 /app/scripts/generate_sandbox_context.py

# Check outputs
ls -lh /app/sandbox_context.*
cat /app/sandbox_context.json | jq '.version'

# Run validation tests
python3 /app/scripts/test_context_generation.py
```

**Expected Results:**

```
✓ Scanning sandbox environment...
✓ Environment scan complete!
✓ Context saved to /app/sandbox_context.json
✓ Markdown context saved to /app/sandbox_context.md
✓ Sandbox context generation complete

Test Results:
==========================================================
Results: 10 passed, 0 failed
==========================================================
```

---

### Step 4: Deploy to Development

Start the full development stack with the new context system.

**Start Services:**

```bash
# Stop existing services
./dev.sh down

# Start with new images
./dev.sh up -d

# Monitor logs
./dev.sh logs -f sandbox
```

**Watch for Context Generation:**

```bash
# Filter supervisord logs for context generation
docker logs pythinker-sandbox 2>&1 | grep context_generator

# Expected output:
# [context_generator] Scanning sandbox environment...
# [context_generator] Environment scan complete!
# [context_generator] Context saved to /app/sandbox_context.json
# [context_generator] ✓ Sandbox context generation complete
# [context_generator] exited: context_generator (exit status 0; expected)
```

---

### Step 5: Validate Agent Integration

Test that agents receive and use the pre-loaded context.

**Backend API Test:**

```python
# In Python shell or script
import requests

# Create a test session
response = requests.put("http://localhost:8000/api/v1/sessions", json={
    "workflow": "planact"
})
session_id = response.json()["session_id"]

# Send a task that would normally trigger exploration
response = requests.post(
    f"http://localhost:8000/api/v1/sessions/{session_id}/chat",
    json={
        "message": "Write a Python script to fetch data from an API"
    },
    stream=True
)

# Monitor tool calls - should NOT see:
# ❌ shell_exec("python3 --version")
# ❌ shell_exec("pip list | grep requests")

# Should see direct action:
# ✓ file_write("script.py", ...)
# ✓ shell_exec("pip install requests")  # Only if not in context
# ✓ shell_exec("python3 script.py")
```

**Check System Prompt:**

```python
from app.domain.services.prompts.system import build_system_prompt

# Build prompt
prompt = build_system_prompt()

# Verify context included
assert "sandbox_environment_knowledge" in prompt.lower()
assert "Python 3.11" in prompt or "Python 3.10" in prompt
assert "DO NOT use exploratory commands" in prompt

print("✓ System prompt includes context")
```

**Check Context Stats:**

```python
from app.domain.services.prompts.sandbox_context import SandboxContextManager

stats = SandboxContextManager.get_context_stats()

print(f"Context available: {stats['available']}")
print(f"Version: {stats['version']}")
print(f"Python packages: {stats['package_counts']['python']}")
print(f"Node packages: {stats['package_counts']['nodejs']}")

# Expected output:
# Context available: True
# Version: 1.0.0
# Python packages: 156
# Node packages: 24
```

---

### Step 6: Measure Impact

Compare agent behavior before and after context system.

**Metrics to Track:**

1. **Token Usage**
   - Before: Count tokens in sessions without context
   - After: Count tokens in sessions with context
   - Expected: 20-40% reduction

2. **Exploratory Commands**
   - Before: Count `shell_exec` calls checking environment
   - After: Should be zero exploratory commands
   - Expected: 5-15 fewer commands per session

3. **Time to First Action**
   - Before: Time from user message to first tool call
   - After: Should be significantly faster
   - Expected: 50-80% reduction

**Example Measurement:**

```python
import time
from app.domain.repositories.mongo.session_repository import MongoSessionRepository

repo = MongoSessionRepository()

# Get sessions from last 24 hours
sessions = repo.get_recent_sessions(limit=100)

exploratory_patterns = [
    "python3 --version",
    "which git",
    "pip list",
    "node --version",
    "npm list",
]

for session in sessions:
    events = repo.get_session_events(session.id)
    tool_calls = [e for e in events if e.type == "tool"]

    exploratory_count = 0
    for tool in tool_calls:
        if tool.tool_name == "shell_exec":
            cmd = tool.tool_input.get("command", "")
            if any(pattern in cmd for pattern in exploratory_patterns):
                exploratory_count += 1

    print(f"Session {session.id}: {exploratory_count} exploratory commands")
```

---

### Step 7: Deploy to Production

Once validated in development, deploy to production.

**Pre-deployment Checklist:**

- [ ] Context generation tested in dev
- [ ] Agent behavior validated
- [ ] Token savings measured
- [ ] No regressions in functionality
- [ ] Documentation reviewed

**Deployment:**

```bash
# Build production images
./build.sh

# Deploy
./run.sh down
./run.sh up -d

# Monitor startup
./run.sh logs -f sandbox | grep context

# Verify health
curl http://localhost:8000/health
```

---

## Rollback Plan

If issues occur, revert to previous behavior:

**Option 1: Disable Context in Prompts (Quick)**

```python
# In backend/app/domain/services/prompts/system.py

# Find this line:
prompt = build_system_prompt()

# Change to:
prompt = build_system_prompt(include_sandbox_context=False)
```

**Option 2: Remove Context Generation (Thorough)**

```bash
# Edit supervisord.conf
# Comment out or remove the [program:context_generator] section

# Restart sandbox
docker restart pythinker-sandbox
```

**Option 3: Full Rollback**

```bash
# Revert to previous git commit
git revert HEAD

# Rebuild
./build.sh

# Redeploy
./run.sh down
./run.sh up -d
```

---

## Troubleshooting

### Issue: Context file not generated

**Symptoms:**
- No `/app/sandbox_context.json` in container
- Agent still using exploratory commands

**Solution:**

```bash
# Check supervisord logs
docker exec pythinker-sandbox supervisorctl status context_generator

# Manually generate
docker exec -u ubuntu pythinker-sandbox python3 /app/scripts/generate_sandbox_context.py

# Check file
docker exec pythinker-sandbox ls -l /app/sandbox_context.json
```

### Issue: Context not loaded by backend

**Symptoms:**
- Context file exists but fallback prompt used
- Stats show `available: false`

**Solution:**

```bash
# Check backend can access file
docker exec pythinker-backend python3 -c "
from app.domain.services.prompts.sandbox_context import SandboxContextManager
print(SandboxContextManager.get_context_stats())
"

# Verify file path
docker exec pythinker-backend ls -l /app/sandbox_context.json

# Check file permissions
docker exec pythinker-sandbox ls -l /app/sandbox_context.json
```

### Issue: Agents still using exploratory commands

**Symptoms:**
- Context loaded correctly but agents still explore

**Solution:**

This may indicate the system prompt isn't being used. Check:

```python
from app.domain.services.agents.base import BaseAgent
from app.domain.services.prompts.system import build_system_prompt

# Verify agent receives context
agent = BaseAgent(...)
prompt = agent.system_prompt

# Should contain context section
assert "sandbox_environment_knowledge" in prompt.lower()
```

---

## Verification Checklist

After deployment, verify:

- [ ] Context file generated on sandbox startup
- [ ] Context contains accurate environment data
- [ ] Backend loads context successfully
- [ ] System prompt includes context section
- [ ] Agents receive pre-loaded knowledge
- [ ] No exploratory commands in new sessions
- [ ] Token usage reduced by 20-40%
- [ ] Time to first action reduced
- [ ] No functional regressions

---

## Next Steps

1. **Monitor Production**
   - Track token usage metrics
   - Monitor error rates
   - Collect user feedback

2. **Iterate**
   - Add more environment details if needed
   - Optimize prompt section size
   - Implement dynamic updates

3. **Document Wins**
   - Calculate ROI (token savings * cost)
   - Share metrics with team
   - Update user documentation

---

## Support

For issues or questions:

1. Check documentation: `/docs/SANDBOX_CONTEXT_SYSTEM.md`
2. Review logs: `docker logs pythinker-sandbox`
3. Run tests: `python3 /app/scripts/test_context_generation.py`
4. File issue on GitHub

---

## Success Criteria

The migration is successful when:

✅ Context files generated automatically at startup
✅ Agents receive pre-loaded environment knowledge
✅ Zero exploratory commands in sessions
✅ 20-40% reduction in token usage
✅ Faster time to first action
✅ No increase in error rates

**Estimated Impact:**
- **Token Savings:** 500-3000 tokens per session
- **Cost Savings:** $15-25/month (1000 sessions)
- **Latency Reduction:** 10-30 seconds per session
- **User Experience:** Immediate task execution

---

## Conclusion

The Sandbox Context System is a high-impact optimization that:

1. **Reduces waste** - Eliminates exploratory token consumption
2. **Improves speed** - Agents act immediately
3. **Enhances reliability** - Complete environment knowledge
4. **Saves costs** - 20-40% token reduction

Deploy with confidence following this guide!
