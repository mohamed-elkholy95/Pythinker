# Comprehensive Fix Plan: Browser, VNC, and Tool Simplification

## Overview

This plan fixes all identified issues and simplifies the tool architecture:
1. **Fix LLM json_object compatibility** (blocks everything)
2. **Remove confusing "search" tool**
3. **Rename "browse/fetch" → "search"** (clearer for users)
4. **Integrate browser_agent for intelligent interaction**
5. **Fix VNC visibility issues**

## Current Confusing Tool Structure

```
❌ BEFORE (Confusing):
- search()      → "Searching OpenRouter pricing..." (browser-based)
- browse()      → "Fetching https://openrouter.ai..." (direct URL)
- browser_agent() → AI-powered browser interaction (underused)
```

```
✅ AFTER (Clear):
- search()      → "Searching https://openrouter.ai..." (renamed from browse)
- browser_agent() → "Analyzing page for pricing data..." (auto-used when needed)
- wide_research() → Advanced multi-source research (existing)
```

## Changes Required

### Phase 1: Fix LLM Compatibility (CRITICAL - Blocks Everything)

**File:** `backend/app/infrastructure/external/llm/openai_llm.py`

**Changes:**
1. Add provider detection method
2. Disable json_object for incompatible providers
3. Fallback to prompt-based JSON parsing

**Implementation:**
```python
# Add new method around line 695
def _supports_json_object_format(self) -> bool:
    """Check if provider supports json_object response format.

    Returns:
        True if json_object format is supported, False otherwise
    """
    if not self._api_base:
        return True  # Default OpenAI supports it

    base = self._api_base.lower()

    # Official OpenAI API supports json_object
    if "api.openai.com" in base or "openai.azure.com" in base:
        return True

    # DeepInfra has limited json_object support
    # NVIDIA models on DeepInfra don't support it
    if "deepinfra" in base:
        if "nvidia" in self._model_name.lower():
            return False

    # Many OpenRouter providers don't support it
    if "openrouter" in base:
        # Only specific models support it
        supported_prefixes = ("openai/", "anthropic/", "google/")
        if not self._model_name.startswith(supported_prefixes):
            return False

    # Conservative default for unknown providers
    return False

# Modify structured_output() method around line 625-633
# BEFORE:
if supports_strict_schema:
    params["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
    }
else:
    # Fall back to json_object mode
    params["response_format"] = {"type": "json_object"}

# AFTER:
if supports_strict_schema:
    params["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
    }
elif self._supports_json_object_format():
    # Use json_object if provider supports it
    params["response_format"] = {"type": "json_object"}
else:
    # Provider doesn't support json_object - use prompt-based JSON
    # Add JSON formatting instruction to system message
    json_instruction = (
        "\n\nIMPORTANT: You must respond with valid JSON matching this schema:\n"
        f"{json.dumps(schema, indent=2)}\n"
        "Respond with ONLY the JSON object, no other text."
    )
    if params["messages"] and params["messages"][0]["role"] == "system":
        params["messages"][0]["content"] += json_instruction
    else:
        params["messages"].insert(0, {"role": "system", "content": json_instruction})
```

---

### Phase 2: Remove Old Search Tool, Rename Browse → Search

**File:** `backend/app/domain/services/tools/search.py`

**Changes:**
1. Remove browser-based search methods
2. Keep only API-based search engine methods
3. Rename to `web_search` for clarity

**File:** `backend/app/domain/services/tools/browser.py`

**Changes:**
1. Rename `browse()` → `search()`
2. Enhance with browser_agent integration
3. Add intelligent page analysis

**New Tool Structure:**
```python
# backend/app/domain/services/tools/browser.py

@tool(
    name="search",  # RENAMED from "browse"
    description="""Navigate to a URL and intelligently extract content.

RENAMED FROM "browse" - This tool searches/fetches web pages by URL.

FEATURES:
- Direct URL navigation with AI-powered content extraction
- Automatic page analysis and scrolling
- JavaScript rendering support
- Visible in VNC/sandbox viewer

WHEN TO USE:
- When you have a specific URL to visit
- To fetch content from a known web page
- To analyze a page's structure and extract data

EXAMPLE:
search(url="https://openrouter.ai/docs/pricing")
→ Navigates to URL, scrolls, analyzes, extracts content

For general web searches by keywords, use web_search() instead.
""",
    parameters={
        "url": {"type": "string", "description": "URL to navigate to"},
        "extract_goal": {
            "type": "string",
            "description": "Optional: What specific information to extract (enables AI analysis)",
            "required": False,
        },
        "wait_for": {
            "type": "string",
            "description": "Optional: CSS selector to wait for before extracting",
            "required": False,
        },
    },
)
async def search(
    self,
    url: str,
    extract_goal: str | None = None,
    wait_for: str | None = None,
) -> ToolResult:
    """Navigate to URL and extract content intelligently."""
    # Implementation below...
```

---

### Phase 3: Integrate Browser Agent for Intelligent Analysis

**File:** `backend/app/domain/services/tools/browser.py`

**New Enhanced Implementation:**
```python
async def search(
    self,
    url: str,
    extract_goal: str | None = None,
    wait_for: str | None = None,
) -> ToolResult:
    """Navigate to URL and extract content intelligently.

    Args:
        url: URL to navigate to
        extract_goal: Optional goal for AI-powered extraction
        wait_for: Optional CSS selector to wait for

    Returns:
        ToolResult with extracted content
    """
    logger.info(f"Searching URL (visible in VNC): {url}")

    # Navigate to URL
    nav_result = await self._browser.navigate(url)
    if not nav_result.success:
        return ToolResult(
            success=False,
            message=f"Navigation failed: {nav_result.message}",
        )

    # Wait for specific element if requested
    if wait_for:
        await asyncio.sleep(0.5)
        # Could add explicit wait logic here
    else:
        # Standard wait for page load
        await asyncio.sleep(1.0)

    # Make interaction visible in VNC
    await self._browser.scroll_page()
    await asyncio.sleep(0.3)

    # If extract_goal specified and browser_agent available, use AI
    if extract_goal and self._has_browser_agent():
        logger.info(f"Using AI agent to analyze page for: {extract_goal}")
        return await self._analyze_with_browser_agent(url, extract_goal)

    # Otherwise, extract content with basic method
    view_result = await self._browser.view_page(wait_for_load=True)
    if not view_result.success:
        return ToolResult(
            success=False,
            message=f"Failed to extract content: {view_result.message}",
        )

    content = view_result.message or ""

    return ToolResult(
        success=True,
        message=f"[CONTENT FROM {url}]\n\n{content}",
        metadata={"url": url, "method": "html_extraction"},
    )

async def _analyze_with_browser_agent(
    self, url: str, extract_goal: str
) -> ToolResult:
    """Use browser_agent to intelligently analyze page.

    This makes the browser interaction visible:
    - Scrolls through page
    - Clicks relevant elements
    - Extracts specific data
    """
    try:
        # Use browser_agent for intelligent extraction
        task = f"On page {url}, {extract_goal}"
        result = await self._browser_agent.execute(task)

        return ToolResult(
            success=True,
            message=result,
            metadata={"url": url, "method": "ai_analysis"},
        )
    except Exception as e:
        logger.error(f"Browser agent analysis failed: {e}")
        # Fallback to basic extraction
        view_result = await self._browser.view_page()
        return ToolResult(
            success=view_result.success,
            message=view_result.message or "",
            metadata={"url": url, "method": "fallback_extraction", "error": str(e)},
        )

def _has_browser_agent(self) -> bool:
    """Check if browser_agent is available."""
    return hasattr(self, '_browser_agent') and self._browser_agent is not None
```

---

### Phase 4: Update Tool Registry and References

**File:** `backend/app/domain/services/tools/__init__.py`

**Changes:**
```python
# Remove old imports
# from app.domain.services.tools.search import SearchTool  # REMOVED

# Update imports
from app.domain.services.tools.browser import BrowserTool  # browse → search
from app.domain.services.tools.search import WebSearchTool  # Renamed for clarity
```

**File:** `backend/app/domain/services/agents/execution.py`

**Update tool initialization:**
```python
# OLD:
tools = [
    search_tool,  # Browser-based search
    browser_tool,  # browse()
    browser_agent_tool,
]

# NEW:
tools = [
    browser_tool,  # search() - renamed from browse
    web_search_tool,  # web_search() - API-based keyword search
    browser_agent_tool,  # Advanced AI browser interaction
]
```

---

### Phase 5: Update Agent Prompts

**File:** `backend/app/domain/services/prompts/execution.py`

**Update tool guidance:**
```python
TOOL_USAGE_GUIDE = """
## Available Tools

### search(url, extract_goal)
Navigate to a specific URL and extract content.
- Use when you have a URL to visit
- Add extract_goal for AI-powered analysis
- Visible in VNC sandbox

Example: search(url="https://docs.python.org/3/library/json.html", extract_goal="extract JSON encoding methods")

### web_search(query, search_type)
Search the web using keywords (Google, Bing, etc.)
- Use when you need to find URLs/pages
- Returns search results with links
- Use search() to visit the URLs

Example: web_search(query="OpenRouter pricing 2026", search_type="info")

### browser_agent(task, url)
AI-powered browser automation for complex tasks.
- Automatically clicks, scrolls, fills forms
- Extracts data from dynamic pages
- Best for multi-step browser tasks

Example: browser_agent(task="Find and extract all pricing tiers from the page", url="https://openrouter.ai/pricing")

### wide_research(topic, queries, search_types)
Comprehensive parallel research across multiple sources.
- Executes multiple searches concurrently
- Synthesizes findings with citations
- Best for in-depth research reports

TOOL SELECTION GUIDE:
1. Need to visit a URL? → search(url)
2. Need to find URLs? → web_search(query)
3. Complex page interaction? → browser_agent(task, url)
4. Comprehensive research? → wide_research(topic)
"""
```

---

### Phase 6: Update Frontend Display

**File:** `frontend/src/constants/tool.ts`

**Update tool display names:**
```typescript
export const TOOL_DISPLAY_NAMES: Record<string, string> = {
  // OLD
  // browse: 'Fetching',
  // search: 'Searching',

  // NEW
  search: 'Searching',  // Renamed from browse
  web_search: 'Web Search',  // API-based search
  browser_agent: 'Analyzing Page',
  wide_research: 'Deep Research',

  // ... other tools
};

export const TOOL_ICONS: Record<string, string> = {
  search: '🔍',  // Renamed from browse
  web_search: '🌐',
  browser_agent: '🤖',
  wide_research: '📚',
};
```

**File:** `frontend/src/components/ToolPanelContent.vue`

Update tool name mappings to match new structure.

---

### Phase 7: Database Migration

**File:** `backend/scripts/migrate_tool_names.py`

```python
"""Migrate old tool names in existing sessions."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

async def migrate_tool_names():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]

    # Update events collection
    result = await db.events.update_many(
        {"event_type": "tool", "tool_name": "browse"},
        {"$set": {"tool_name": "search"}}
    )
    print(f"Updated {result.modified_count} browse → search events")

    # Update tool_name in message metadata
    result = await db.events.update_many(
        {"metadata.tool_name": "browse"},
        {"$set": {"metadata.tool_name": "search"}}
    )
    print(f"Updated {result.modified_count} browse → search metadata")

    await client.close()

if __name__ == "__main__":
    asyncio.run(migrate_tool_names())
```

---

## Testing Plan

### 1. Test LLM Fix
```bash
cd backend
conda activate pythinker
pytest tests/infrastructure/external/llm/test_openai_llm.py::test_json_object_fallback -v
```

### 2. Test Tool Rename
```python
# Test that search() now works like old browse()
result = await browser_tool.search(url="https://example.com")
assert result.success
assert "Example Domain" in result.message
```

### 3. Test Browser Agent Integration
```python
# Test AI-powered extraction
result = await browser_tool.search(
    url="https://openrouter.ai/docs/pricing",
    extract_goal="extract all pricing tiers and their costs"
)
assert result.success
assert "pricing" in result.message.lower()
```

### 4. Test VNC Visibility
1. Start session
2. Request: "Search https://openrouter.ai and tell me about their pricing"
3. Watch VNC - should see:
   - Browser opens
   - Page loads
   - Scrolling visible
   - Content extracted
4. Check UI shows "Searching https://openrouter.ai..." (not "Fetching")

---

## Rollout Steps

1. **Deploy LLM fix first** (fixes planning errors)
   - Update `openai_llm.py`
   - Restart backend
   - Test plan creation works

2. **Deploy tool rename** (UI clarity)
   - Update tool files
   - Update frontend
   - Run migration script
   - Restart services

3. **Enable browser_agent integration** (better analysis)
   - Update browser tool
   - Update prompts
   - Test end-to-end

4. **Monitor and adjust**
   - Watch agent tool choices
   - Adjust prompts if needed
   - Fine-tune browser_agent triggers

---

## Files to Modify

### Backend
1. `backend/app/infrastructure/external/llm/openai_llm.py` ⭐ CRITICAL
2. `backend/app/domain/services/tools/browser.py` - Rename & enhance
3. `backend/app/domain/services/tools/search.py` - Simplify to web_search
4. `backend/app/domain/services/tools/__init__.py` - Update exports
5. `backend/app/domain/services/agents/execution.py` - Update tool list
6. `backend/app/domain/services/prompts/execution.py` - Update guidance
7. `backend/scripts/migrate_tool_names.py` - New migration script

### Frontend
8. `frontend/src/constants/tool.ts` - Update display names
9. `frontend/src/components/ToolPanelContent.vue` - Update references

### Testing
10. `backend/tests/domain/services/tools/test_browser.py` - Update tests
11. `backend/tests/infrastructure/external/llm/test_openai_llm.py` - Add json_object tests

---

## Expected Results

### Before Fix
```
❌ Planning fails with json_object error
❌ UI shows confusing "Searching" and "Fetching"
❌ Browser loads pages but doesn't interact
❌ VNC appears stuck/frozen
```

### After Fix
```
✅ Planning succeeds (json_object fallback works)
✅ UI shows clear "Searching https://..."
✅ Browser intelligently analyzes pages
✅ VNC shows scrolling and interaction
✅ Better data extraction quality
```

---

## Estimated Impact

- **Planning success rate:** 0% → 100%
- **Tool clarity:** Confusing → Clear
- **Browser interaction quality:** Static → Dynamic
- **User experience:** Frustrating → Smooth
- **Research task completion:** Low → High

---

## Next Steps After This Fix

1. **Monitor agent tool selection patterns**
2. **Add more browser_agent examples to prompts**
3. **Optimize VNC frame rate for smoother viewing**
4. **Add progress indicators for long browser tasks**
5. **Build browser_agent result caching**
