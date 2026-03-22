---
name: browser-automation
description: Browser tool and CDP screencast architecture — Playwright, Chrome DevTools Protocol, BrowserTool vs BrowserAgentTool patterns
---

# Browser Automation Skill

## When to Use
When working with browser-related code, CDP streaming, or browser tool implementations.

## Three-Tier Architecture

```
Domain Protocol (backend/app/domain/services/browser/browser.py)
    ↓ defines interface
Infrastructure (backend/app/infrastructure/browser/playwright_browser.py)
    ↓ implements with Playwright
Tool Services (backend/app/domain/services/tools/browser_tool.py, browser_agent_tool.py)
    ↓ exposes to LLM
```

## Browser Tools

### BrowserTool (Manual Control)
Single actions: navigate, click, input, screenshot, extract text
- Agent decides each action
- Returns result after each step

### BrowserAgentTool (Autonomous)
Multi-step workflows via browser-use library
- Agent provides goal, tool executes autonomously
- Reports progress via events

## CDP Screencast
- `SANDBOX_STREAMING_MODE=cdp_only`
- WebSocket on port 9222
- Real-time frame streaming to frontend via SSE
- Health monitoring in `SandboxHealth`

## Key Patterns
- **Crash recovery**: Automatic browser restart with progress events
- **Connection pooling**: `HTTPClientPool` for all HTTP to sandbox (60-75% latency reduction)
- **Timeout**: `asyncio.timeout()` for all browser operations
- **Error handling**: Non-blocking try/except wrapping all CDP calls

## Playwright Setup
- Engine: Playwright Chromium (lighter than Chrome for Testing)
- Install: Only `chromium` browser (no Firefox/WebKit needed)
- `uvicorn[standard]` required in sandbox for WebSocket support
