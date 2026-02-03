# Browser & VNC Display Issues Report
**Generated:** 2026-02-03 17:17:00
**Session ID:** 0d403d8837874172

## Summary

🔴 **Critical Issues Found:**
1. **LLM Provider Compatibility** - Plan creation fails (blocks entire workflow)
2. **Browser Agent Not Interacting** - Agent opens pages but doesn't click/analyze
3. **VNC Display Issue** - Browser content appears stuck/not showing results

---

## Issue #1: Browser Agent Not Actually Clicking/Analyzing Pages

### Problem Description
The agent opens browser pages successfully (visible in VNC), but it's **NOT actually interacting** with the content:
- ✅ Browser opens search results
- ✅ CDP brings page to front
- ❌ **No clicking on links**
- ❌ **No scrolling or analyzing**
- ❌ **Just static HTML scraping**

### Root Cause

The agent is using the basic **`search` tool** which:
1. Opens browser to search page
2. Calls `view_page()` to scrape HTML
3. Returns raw content
4. **Does NOT interact with the page**

The **`browser_agent` tool** is ENABLED but NOT being used:
```
[info] Browser agent tool enabled for Agent 912f13ad9b464d25
```

However, the execution agent is calling `search` instead of `browser_agent`:
```
[info] Tool invocation started
[info] Browser search (visible in VNC): OpenRouter free tier token pricing 2026
```

### Why This Happens

1. **Search tool implementation** (backend/app/domain/services/tools/search.py:345-375):
```python
# Navigate to search page
nav_result = await self._browser.navigate(search_url)

# Wait briefly for page load
await asyncio.sleep(1.0)

# Get page content (JUST SCRAPING HTML)
view_result = await self._browser.view_page(wait_for_load=True)
content = view_result.message if view_result.message else ""
```

2. **Browser agent tool** (backend/app/domain/services/tools/browser_agent.py):
   - Uses `browser_use` library (AI-powered browser interaction)
   - Would actually click, scroll, analyze, navigate
   - **Is enabled but agent LLM doesn't choose to use it**

### Impact
- Search results visible in VNC but appear "stuck"
- Agent cannot extract data from dynamic/interactive pages
- Cannot click through to individual result pages
- Research tasks fail or return incomplete data

### Solution Options

**Option 1: Make search tool use browser_agent internally**
```python
# In search.py _search_via_browser()
# After navigating to search results:
if self._has_browser_agent():
    # Use AI agent to analyze results and click relevant links
    task = f"Analyze search results for '{query}' and extract key information"
    return await self._browser_agent.execute(task)
else:
    # Fallback to HTML scraping
    return await self._browser.view_page()
```

**Option 2: Update agent prompts to prefer browser_agent**
- Modify execution prompts to suggest `browser_agent` for research tasks
- Add examples showing when to use `browser_agent` vs `search`

**Option 3: Create hybrid search_and_analyze tool**
- Combines search + browser_agent
- Automatically clicks top results and extracts content

---

## Issue #2: VNC Display Appears Stuck

### Symptoms
User reports: "search not showing anything on VNC as if its stuck"

### Evidence from Logs
- VNC WebSocket connections opening/closing rapidly:
```
[info] Web -> VNC connection closed
[info] WebSocket connection closed
```
- Browser bringing pages to front via CDP:
```
[info] Brought page to front via CDP for VNC visibility
```
- But user sees no interaction/movement

### Root Cause
The browser IS working, but:
1. It navigates to search results
2. Scrapes HTML (invisible to user)
3. Doesn't click or scroll (so appears frozen)
4. VNC connection closes before user sees activity

### Why Pages Appear "Stuck"
1. Browser loads search results
2. `view_page()` extracts HTML immediately (< 1 second)
3. No visual interaction occurs
4. To user, it looks like browser loaded then froze

### Solution
Make browser interactions visible:
```python
# After navigation
await self._browser.scroll_page()  # Show scrolling
await asyncio.sleep(0.5)  # Let user see the page
# Then analyze/click
```

---

## Issue #3: Search Getting 404 Errors

### Evidence
```
[warning] Navigation to https://medium.com/a-practical-guide-to-openrouter-u returned status 404
[warning] Navigation to https://analyticsvidhya.com/blog/2026/01/top-13-free-ai-models-on-openrouter returned status 404
```

### Analysis
- Search engine returning future-dated URLs (2026/01)
- Links are speculative/hallucinated by search
- Agent trying to visit non-existent pages

### Impact
- Wasted time navigating to 404 pages
- Reduced research quality
- Agent confusion

### Solution
1. Add 404 detection and skip
2. Validate URLs before navigation
3. Use multiple search engines (fallback)

---

## Technical Details

### Browser Flow (Current - Broken)
```
1. Agent calls search("OpenRouter pricing")
2. Search tool navigates to google.com/search?q=...
3. Page loads in VNC (user can see it)
4. search tool calls view_page() - scrapes HTML
5. Returns HTML text to agent
6. Page appears frozen (no clicks/scrolls)
```

### Browser Flow (Expected - Working)
```
1. Agent calls browser_agent("Research OpenRouter pricing")
2. browser_agent navigates to google.com/search?q=...
3. Page loads in VNC (user can see it)
4. AI analyzes search results (visible thinking)
5. Clicks on relevant link (user sees click)
6. Scrolls and reads content (user sees scrolling)
7. Extracts structured data
8. Returns findings to agent
```

### Tool Availability
From logs:
```
[info] Browser agent tool enabled for Agent 912f13ad9b464d25
```

Available tools to agent:
- ✅ `search` - Basic browser search (used)
- ✅ `browser_agent` - AI browser interaction (available but unused)
- ✅ `browse` - Simple URL navigation
- ✅ Other tools (file, shell, etc.)

### Why Agent Doesn't Use browser_agent

**Possible reasons:**
1. **Prompt engineering** - Execution prompt doesn't emphasize browser_agent
2. **Tool descriptions** - search tool description more appealing
3. **Cost/speed trade-off** - search is faster (LLM avoiding slow tool)
4. **Model limitations** - NVIDIA Nemotron may not reason well about tool choice

---

## Immediate Fixes Needed

### Priority 1: Fix LLM Provider (Blocks Everything)
```python
# backend/app/infrastructure/external/llm/openai_llm.py:633
# Add DeepInfra detection before using json_object
def _supports_json_object_format(self) -> bool:
    if "deepinfra" in (self._api_base or "").lower():
        return False  # DeepInfra doesn't support it
    return True

# Then use it:
if supports_strict_schema:
    params["response_format"] = {"type": "json_schema", ...}
elif self._supports_json_object_format():
    params["response_format"] = {"type": "json_object"}
# else: use prompt-based JSON
```

### Priority 2: Make Browser Interactions Visible
```python
# backend/app/domain/services/tools/search.py
async def _search_via_browser(self, query: str, date_range: str | None = None):
    # Navigate
    await self._browser.navigate(search_url)

    # Make interaction visible
    await asyncio.sleep(1.0)  # Let page load visually
    await self._browser.scroll_page()  # Show scrolling

    # If browser_agent available, use it
    if hasattr(self, '_browser_agent') and self._browser_agent:
        return await self._use_browser_agent_for_search(query)

    # Otherwise fallback to HTML scraping
    return await self._browser.view_page()
```

### Priority 3: Update Agent Prompts
Add to execution prompt:
```
For research tasks involving web pages:
- Use browser_agent("task description") for interactive analysis
- Use search("query") only for quick text searches
- browser_agent can click links, scroll, and analyze dynamic content
```

---

## Files to Modify

1. **backend/app/infrastructure/external/llm/openai_llm.py**
   - Line 633: Add json_object format detection
   - Add `_supports_json_object_format()` method

2. **backend/app/domain/services/tools/search.py**
   - Line 345-375: Enhance `_search_via_browser()`
   - Add browser_agent integration
   - Add visual delays for VNC visibility

3. **backend/app/domain/services/prompts/execution.py**
   - Update tool usage guidance
   - Emphasize browser_agent for research

4. **backend/app/domain/services/tools/browser_agent.py**
   - Ensure proper error handling
   - Add VNC visibility logging

---

## Verification Steps

After fixes:
1. Start new session
2. Request research task
3. Observe VNC - should see:
   - Browser opening
   - Scrolling/clicking visible
   - Multiple pages navigated
   - Clear progress indication
4. Check agent response:
   - Contains structured data
   - Has proper citations
   - No 404 errors

---

## Current System State

**Healthy Components:**
- ✅ VNC server (port 5900)
- ✅ CDP screencast (port 8222)
- ✅ Chromium browser processes running
- ✅ WebSocket VNC proxy working
- ✅ browser_agent tool loaded

**Broken Components:**
- ❌ LLM structured output (json_object not supported)
- ❌ Browser interaction logic (not using browser_agent)
- ❌ Visual feedback (appears stuck to user)
- ❌ Search result navigation (404 errors)

---

## Next Steps

1. **Immediate:** Fix DeepInfra json_object compatibility
2. **Short-term:** Integrate browser_agent into search workflow
3. **Medium-term:** Improve VNC visual feedback
4. **Long-term:** Build hybrid search+analyze tool
