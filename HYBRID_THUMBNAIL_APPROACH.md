# Hybrid Thumbnail Approach - Best Practice

## Strategy: Screenshots for Thumbnails + Live VNC for Detail

### Architecture

```
┌─────────────────────────────────────┐
│   Collapsed Progress Bar            │
│  ┌──────┐                          │
│  │ 📸   │ Last screenshot          │
│  │ IMG  │ (lightweight)            │
│  └──────┘                          │
└─────────────────────────────────────┘

        ↓ Click to expand

┌─────────────────────────────────────┐
│   Expanded View / Full Panel        │
│  ┌───────────────────┐              │
│  │  🎥 LIVE VNC      │              │
│  │  Real-time stream │              │
│  │  (on-demand)      │              │
│  └───────────────────┘              │
└─────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Screenshot System (2-3 hours)

**Priority:** High
**Impact:** Major UX improvement

#### 1.1 Sandbox Screenshot API

**File:** `sandbox/app/api/vnc.py` (new)

```python
from fastapi import APIRouter, HTTPException, Response
import subprocess
import logging
import asyncio

router = APIRouter(prefix="/vnc", tags=["VNC"])
logger = logging.getLogger(__name__)

@router.get("/screenshot")
async def capture_screenshot(
    quality: int = 85,  # JPEG quality (faster than PNG)
    scale: float = 0.5  # Scale down for thumbnail
):
    """Capture desktop screenshot optimized for thumbnails"""
    try:
        # Use xwd + convert for fast capture with scaling
        cmd = [
            "sh", "-c",
            f"DISPLAY=:99 xwd -root | "
            f"convert xwd:- -scale {int(scale*100)}% "
            f"-quality {quality} jpg:-"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)

        if proc.returncode != 0:
            raise Exception(f"Screenshot failed: {stderr.decode()}")

        return Response(
            content=stdout,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache",
                "X-Thumbnail-Size": str(len(stdout))
            }
        )

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Screenshot timeout")
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Register router:**
```python
# sandbox/app/api/router.py
from app.api import vnc

api_router.include_router(vnc.router)
```

#### 1.2 Backend Screenshot Capture

**File:** `backend/app/domain/services/agents/base.py`

```python
async def _capture_screenshot_if_needed(
    self,
    tool_name: str,
    tool_call_id: str
) -> Optional[str]:
    """Capture screenshot for visual tools"""

    # Tools that benefit from screenshots
    VISUAL_TOOLS = {
        'shell_exec', 'shell_view', 'shell_write_to_process',
        'code_run', 'code_execute', 'code_submit',
        'browser_navigate', 'browser_click', 'browser_type'
    }

    if tool_name not in VISUAL_TOOLS:
        return None

    try:
        # Get screenshot from sandbox (JPEG, scaled 50%, ~20-40KB)
        response = await self.sandbox_client.get(
            f"/api/v1/vnc/screenshot?quality=75&scale=0.5",
            timeout=5.0
        )

        if response.status_code == 200:
            # Embed as data URL for portability
            import base64
            b64_data = base64.b64encode(response.content).decode()
            return f"data:image/jpeg;base64,{b64_data}"

    except Exception as e:
        logger.debug(f"Screenshot capture failed: {e}")

    return None


# Modify _emit_tool_event (around line 230-250)
async def _emit_tool_event(
    self,
    tool_call_id: str,
    tool_name: str,
    function_name: str,
    function_args: dict,
    status: ToolStatus,
    function_result: Any = None,
) -> None:
    """Emit tool event with optional screenshot"""

    # ... existing event creation code ...

    # Capture screenshot when tool completes
    screenshot_url = None
    if status == ToolStatus.CALLED:
        screenshot_url = await self._capture_screenshot_if_needed(
            function_name,
            tool_call_id
        )

    # Add screenshot to tool content based on tool type
    tool_content = None
    if function_name.startswith('shell_'):
        tool_content = ShellToolContent(
            console=function_result,
            screenshot=screenshot_url  # Add this field
        )
    elif function_name.startswith('browser_'):
        tool_content = BrowserToolContent(
            content=function_result,
            screenshot=screenshot_url  # Add this field
        )

    tool_event = ToolEvent(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        function_name=function_name,
        function_args=function_args,
        status=status,
        function_result=function_result,
        tool_content=tool_content,  # Now includes screenshot
        # ... other fields
    )

    await self._event_emitter.emit(tool_event)
```

#### 1.3 Update Data Models

**File:** `backend/app/domain/models/event.py`

```python
# Add screenshot field to ShellToolContent
class ShellToolContent(BaseModel):
    """Shell tool content"""
    console: Any
    screenshot: Optional[str] = None  # Add this

# CodeToolContent also needs it
class CodeToolContent(BaseModel):
    """Code execution content"""
    result: Any
    screenshot: Optional[str] = None  # Add this
```

#### 1.4 Docker Setup

**File:** `sandbox/Dockerfile`

```dockerfile
# Add imagemagick for screenshot processing
RUN apt-get update && apt-get install -y \
    x11-apps \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*
```

---

### Phase 2: Live VNC in Panel (Optional, 1 hour)

**For when user expands the view**

**File:** `frontend/src/components/TaskProgressBar.vue`

```vue
<template>
  <div v-if="isVisible" class="task-progress-bar">
    <!-- Collapsed: Screenshot thumbnail -->
    <div v-if="!isExpanded" class="relative">
      <div
        v-if="thumbnailUrl"
        class="thumbnail-preview"
        @click="toggleExpand"
      >
        <img :src="thumbnailUrl" alt="Desktop preview" />
        <div class="thumbnail-overlay">
          <MonitorPlay class="w-5 h-5" />
        </div>
      </div>

      <!-- Progress bar... -->
    </div>

    <!-- Expanded: Live VNC -->
    <div v-else class="expanded-view">
      <div class="vnc-container">
        <!-- Option A: Mini VNC viewer -->
        <VNCViewer
          v-if="sessionId && shouldShowLivePreview"
          :session-id="sessionId"
          :width="280"
          :height="160"
          :view-only="true"
          :scale="true"
          class="rounded-lg"
        />

        <!-- Option B: Fallback to screenshot -->
        <img
          v-else-if="thumbnailUrl"
          :src="thumbnailUrl"
          class="rounded-lg"
        />
      </div>

      <!-- Task list... -->
    </div>
  </div>
</template>

<script setup lang="ts">
const shouldShowLivePreview = computed(() => {
  // Only stream VNC when expanded AND task is actively running
  return isExpanded.value && (props.isLoading || props.isThinking);
});
</script>

<style scoped>
.thumbnail-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}

.thumbnail-preview:hover .thumbnail-overlay {
  opacity: 1;
}
</style>
```

---

## Performance Comparison

### Collapsed State (100 users)

| Approach | Bandwidth | CPU | Best For |
|----------|-----------|-----|----------|
| **Screenshot** | ~3 MB/s total | Minimal | ✅ Normal use |
| **Live VNC** | ~200 MB/s total | High | ❌ Not scalable |

### Expanded State (1 user watching)

| Approach | Bandwidth | CPU | Best For |
|----------|-----------|-----|----------|
| **Screenshot** | ~30 KB/s | Minimal | Passive monitoring |
| **Live VNC** | ~2 MB/s | Medium | ✅ Active debugging |

---

## Recommendation Summary

### ✅ Implement Screenshot System First

**Reasons:**
1. **Scalable** - Works for many concurrent users
2. **Historical** - Enables timeline replay with visuals
3. **Efficient** - Low bandwidth, battery friendly
4. **Simple** - 2-3 hours implementation
5. **Portable** - Screenshots work in event logs, exports

### ➕ Add Live VNC Later (Optional)

**Only when:**
- User explicitly expands to full view
- Task is actively running
- User needs real-time visual feedback

**Implementation:**
- Reuse existing VNCViewer component
- Only connect when expanded + running
- Auto-disconnect when collapsed

---

## Migration Path

### Week 1: Screenshot System
```bash
1. Add sandbox screenshot endpoint
2. Capture after tool execution
3. Embed in ToolEvent.tool_content
4. Frontend displays in TaskProgressBar
```

### Week 2+: Optional Enhancements
```bash
1. Add live VNC option in expanded view
2. Implement thumbnail caching
3. Add screenshot history viewer
4. Optimize image compression
```

---

## File Checklist

### Screenshots (Required):
- [ ] `sandbox/app/api/vnc.py` - Screenshot endpoint
- [ ] `sandbox/Dockerfile` - Install imagemagick
- [ ] `backend/app/domain/services/agents/base.py` - Capture logic
- [ ] `backend/app/domain/models/event.py` - Add screenshot fields
- [ ] `sandbox/app/api/router.py` - Register VNC router

### Live VNC (Optional):
- [ ] `frontend/src/components/TaskProgressBar.vue` - Conditional VNC
- [ ] `frontend/src/composables/useVNC.ts` - Connection management

---

## Expected Results

### Before:
```
┌─────────────────┐
│ Task Progress   │
│ No preview   ❌ │
└─────────────────┘
```

### After Screenshots:
```
┌─────────────────┐
│ Task Progress   │
│ [Terminal] 📸✅│
│ Running tests   │
└─────────────────┘
```

### After Full Implementation:
```
Collapsed: 📸 Screenshot (30KB, instant)
Expanded:  🎥 Live VNC (2MB/s, real-time)
```

---

**Bottom line:** Start with screenshots for 80% of use cases, add live VNC only for the 20% that need real-time debugging.
