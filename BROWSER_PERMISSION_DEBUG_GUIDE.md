# Browser Permission Debug Guide

## Issue
When deployed, the agent asks for user permission when trying to use the browser.

## Investigation Summary

After thorough code analysis, here's what was found:

### 1. **Autonomy System Status**
- **Exists**: Yes (`backend/app/domain/services/agents/autonomy_config.py`)
- **Integrated**: **NO** - The autonomy system is defined but never actually used in agent execution
- **Security Assessor**: Always returns `requires_confirmation=False`

### 2. **Likely Causes**

#### A. Browser Permission Prompts (Most Likely)
Websites may request browser permissions for:
- Notifications
- Geolocation
- Camera/Microphone
- Clipboard access
- Storage quotas

**These are browser-level prompts, not agent-level confirmations.**

#### B. Environment Configuration
Different autonomy levels if configured via environment:
- `SUPERVISED`: Requires approval for ALL actions (including browser)
- `GUIDED`: Requires approval for critical actions only (default)
- `AUTONOMOUS`: Minimal approvals
- `UNRESTRICTED`: No approvals

## Solutions Applied

### 1. Added Autonomy Configuration to `.env.dokploy`
```bash
# Autonomy Configuration
AUTONOMY_LEVEL=autonomous  # Changed from default "guided" to "autonomous"
ALLOW_BROWSER_NAVIGATION=true
```

### 2. Added Configuration Template to `.env.example`
For future reference and documentation.

## How to Debug Further

### Step 1: Check Browser Console
When you see a permission prompt, open browser DevTools (F12) and check:
```javascript
// In the browser console
console.log('Permission state:', Notification.permission);
```

### Step 2: Check Backend Logs
Look for these patterns in your deployment logs:
```bash
docker logs pythinker-backend-1 | grep -i "wait\|approval\|confirmation"
```

### Step 3: Check Which Permission is Being Requested
Add this to your browser context configuration in `backend/app/infrastructure/external/browser/playwright_browser.py`:

```python
# Around line 200, in the browser context setup
context = await self._browser.new_context(
    viewport={"width": self.width, "height": self.height},
    user_agent=self._user_agent,
    # Grant all permissions by default
    permissions=[
        'geolocation',
        'notifications',
        'camera',
        'microphone',
        'clipboard-read',
        'clipboard-write'
    ]
)
```

### Step 4: Check Event Stream
Monitor SSE events to see if `WaitEvent` is being emitted:
```bash
# In your deployment, monitor the SSE stream
curl -N http://your-deployment-url/api/v1/sessions/{session_id}/events
```

Look for events like:
```json
{"type": "wait"}
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTONOMY_LEVEL` | `guided` | `supervised`, `guided`, `autonomous`, `unrestricted` |
| `ALLOW_BROWSER_NAVIGATION` | `true` | Enable/disable browser tool |
| `ALLOW_EXTERNAL_REQUESTS` | `true` | Enable/disable external API calls |
| `ALLOW_SHELL_EXECUTE` | `true` | Enable/disable shell commands |

## Testing

### Test 1: Verify Autonomy Level
```bash
# In your deployment environment
docker exec pythinker-backend-1 python -c "
from app.core.config import get_settings
settings = get_settings()
print(f'Autonomy Level: {settings.autonomy_level}')
print(f'Browser Navigation Allowed: {settings.allow_browser_navigation}')
"
```

### Test 2: Check Security Assessor
```python
# Add temporary logging in backend/app/domain/services/agents/base.py
# Around line 965
security_assessment = self._security_assessor.assess_action(function_name, function_args)
logger.info(f"Security assessment for {function_name}: requires_confirmation={security_assessment.requires_confirmation}")
```

### Test 3: Browser Permission Override
Create a test script to verify browser permissions are granted:

```python
# test_browser_permissions.py
from playwright.async_api import async_playwright

async def test_permissions():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            permissions=['geolocation', 'notifications']
        )
        page = await context.new_page()

        # Test notification permission
        result = await page.evaluate('Notification.permission')
        print(f'Notification permission: {result}')

        await browser.close()

import asyncio
asyncio.run(test_permissions())
```

## Next Steps

1. **Redeploy** with the updated `.env.dokploy` configuration
2. **Monitor logs** for any `WaitEvent` or approval requests
3. **Test browser behavior** to see if prompts still appear
4. **Report back** with specific details about:
   - When the prompt appears (which URL, which action)
   - What the prompt says exactly
   - Browser console logs at the time
   - Backend logs showing the event stream

## Additional Notes

### Browser Context Permissions in Playwright
Playwright supports granting permissions at context creation:
- `geolocation`: Location access
- `notifications`: Push notifications
- `camera`: Camera access
- `microphone`: Microphone access
- `clipboard-read`: Read clipboard
- `clipboard-write`: Write to clipboard
- `payment-handler`: Payment API
- `accessibility-events`: Accessibility events
- `background-sync`: Background sync
- `midi`: MIDI device access

### Autonomy System Architecture (Not Currently Used)
The codebase has a comprehensive autonomy system that's **not integrated**:
- `AutonomyLevel`: 4 levels of agent autonomy
- `PermissionFlags`: Fine-grained permission control
- `SafetyLimits`: Iteration, tool call, time, cost limits
- `ApprovalRequest`: User approval workflow

**Future Enhancement**: This system could be integrated into the agent execution flow to provide granular control over agent actions.

## Contact
If the issue persists after these changes, please provide:
1. Screenshot of the permission prompt
2. Browser console logs
3. Backend logs from the time the prompt appears
4. The exact URL being visited when the prompt appears
