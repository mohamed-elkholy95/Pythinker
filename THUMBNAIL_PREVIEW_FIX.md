# Pythinker PC Thumbnail Preview Fix

## Issue Explanation

The **"No preview"** placeholder appeared because the TaskProgressBar thumbnail system expected desktop screenshots, but the backend wasn't capturing them during tool execution.

### Why It Wasn't Working

**Flow:**
```
1. User asks agent to run command
2. Agent executes shell_exec tool in sandbox
3. Tool returns text output only (no screenshot)
4. Frontend receives ToolEvent without screenshot data
5. TaskProgressBar shows "No preview" placeholder
```

**Expected Data Flow:**
```typescript
// Frontend (ChatPage.vue line 511-515)
const currentThumbnailUrl = computed(() => {
  const tool = lastNoMessageTool.value;
  if (!tool?.content?.screenshot) return '';  // ❌ Always empty!
  return tool.content.screenshot;
});
```

**Backend Issue:**
- Tools execute commands but don't capture desktop screenshots
- `ToolEvent.tool_content.screenshot` field is never populated
- No automatic screenshot mechanism exists

---

## ✅ Quick Fix Applied

**What Changed:** Hides thumbnail when no screenshot is available instead of showing "No preview".

### Changes Made:

1. **Collapsed view** (line 13-23):
   ```vue
   <!-- Before: Always show box with "No preview" text -->
   <div class="...">
     <img v-if="thumbnailUrl" :src="thumbnailUrl" />
     <div v-else>No preview</div>  <!-- ❌ Confusing -->
   </div>

   <!-- After: Only show when thumbnail exists -->
   <div v-if="thumbnailUrl" class="...">
     <img :src="thumbnailUrl" />
   </div>
   ```

2. **Expanded view** (line 77-87):
   ```vue
   <!-- Before: Show empty box in expanded view -->
   <div v-if="showExpandedThumbnail" class="...">
     <img v-if="thumbnailUrl" :src="thumbnailUrl" />
     <div v-else>No preview</div>
   </div>

   <!-- After: Only show when thumbnail exists -->
   <div v-if="showExpandedThumbnail && thumbnailUrl" class="...">
     <img :src="thumbnailUrl" />
   </div>
   ```

3. **Layout adjustment** (line 29):
   ```vue
   <!-- Only reserve space for thumbnail when it exists -->
   :class="showCollapsedThumbnail && thumbnailUrl ? 'pl-[156px]' : ''"
   ```

4. **Computed properties** (line 328-337):
   ```typescript
   // Only show thumbnail UI when we have actual screenshot data
   const showCollapsedThumbnail = computed(() => {
     return !!props.sessionId && !!props.thumbnailUrl && !props.hideThumbnail;
   });
   ```

### Result:
- ✅ No more confusing "No preview" placeholder
- ✅ Clean UI when screenshots aren't available
- ✅ Thumbnail appears when backend provides screenshots (future)
- ✅ Layout adapts dynamically

---

## 🚀 Proper Solution (For Full Feature)

To enable **real desktop screenshots**, implement screenshot capturing:

### Step 1: Add Sandbox Screenshot API

**File:** `sandbox/app/api/vnc.py` (new)

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import subprocess
import logging

router = APIRouter(prefix="/vnc", tags=["VNC"])
logger = logging.getLogger(__name__)

@router.get("/screenshot")
async def capture_desktop_screenshot():
    """Capture current desktop screenshot via X11/VNC"""
    try:
        # Use scrot or import to capture X display
        result = subprocess.run(
            ["scrot", "-z", "-"],  # Output to stdout
            capture_output=True,
            timeout=5,
            env={"DISPLAY": ":99"}  # Your VNC display
        )

        if result.returncode != 0:
            raise Exception(result.stderr.decode())

        return Response(
            content=result.stdout,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Register in `sandbox/app/api/router.py`:**
```python
from app.api import vnc  # Add import
api_router.include_router(vnc.router)  # Add router
```

### Step 2: Add Screenshot Capture to Backend

**File:** `backend/app/domain/services/agents/base.py`

Add screenshot capture after tool execution:

```python
async def _capture_desktop_screenshot(self, tool_name: str) -> Optional[str]:
    """Capture desktop screenshot after tool execution"""
    # Only capture for computer-interacting tools
    computer_tools = {'shell_exec', 'shell_view', 'shell_write_to_process',
                      'code_run', 'code_execute'}

    if tool_name not in computer_tools:
        return None

    try:
        # Call sandbox screenshot API
        response = await self.sandbox.get_screenshot()

        if response.status_code == 200:
            # Convert to data URL for embedding
            import base64
            img_data = base64.b64encode(response.content).decode()
            return f"data:image/png;base64,{img_data}"

        return None
    except Exception as e:
        logger.debug(f"Screenshot capture failed: {e}")
        return None


# Modify _emit_tool_event method (around line 236)
async def _emit_tool_event(self, ...):
    # ... existing code ...

    # Capture screenshot for tool content
    screenshot_url = None
    if status == ToolStatus.CALLED:
        screenshot_url = await self._capture_desktop_screenshot(function_name)

    tool_event = ToolEvent(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        function_name=function_name,
        function_args=function_args,
        status=status,
        tool_content={
            "screenshot": screenshot_url,  # Add screenshot here
            # ... other content
        }
    )

    # ... emit event ...
```

### Step 3: Add Sandbox Screenshot Method

**File:** `backend/app/infrastructure/external/sandbox/docker_sandbox.py`

```python
async def get_screenshot(self) -> httpx.Response:
    """Capture current desktop screenshot"""
    try:
        response = await self.client.get(
            f"{self.base_url}/api/v1/vnc/screenshot",
            timeout=10.0
        )
        response.raise_for_status()
        return response
    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
        raise
```

### Step 4: Install scrot in Sandbox

**File:** `sandbox/Dockerfile`

Add to apt-get install line:
```dockerfile
RUN apt-get update && apt-get install -y \
    # ... existing packages ...
    scrot \  # Add this line
    && rm -rf /var/lib/apt/lists/*
```

---

## Testing

### Quick Fix (Current):
```bash
# 1. Refresh frontend (already applied)
# 2. Start a task - no "No preview" should appear
# 3. Thumbnail space only appears if screenshots exist
```

### Full Implementation (After proper fix):
```bash
# 1. Rebuild sandbox with scrot
docker-compose -f docker-compose-development.yml build sandbox

# 2. Test screenshot API
curl http://localhost:8083/api/v1/vnc/screenshot -o test.png

# 3. Start chat session and run command
# 4. TaskProgressBar should show real desktop screenshot
```

---

## Alternative: Use Existing VNC Stream

Instead of capturing screenshots, you could display a **live VNC preview**:

**Pros:**
- Real-time updates
- No backend changes needed
- Uses existing VNC infrastructure

**Cons:**
- Higher bandwidth (WebSocket stream)
- More complex to implement thumbnail-sized VNC viewer
- Performance overhead

**Implementation Sketch:**
```vue
<template>
  <div class="thumbnail-container">
    <!-- Mini VNC viewer in thumbnail -->
    <VNCViewer
      v-if="sessionId && liveVnc"
      :session-id="sessionId"
      :width="140"
      :height="80"
      :view-only="true"
      :scale="true"
    />
  </div>
</template>
```

---

## Recommendation

**Short term:** ✅ **Quick fix applied** - Hide placeholder when no screenshots

**Long term:** 🚀 **Implement screenshot capture** - Better UX, shows what agent is doing

**Timeline:**
- Quick fix: **Done** ✅
- Full implementation: **2-4 hours of development**

---

## Files Modified

### Quick Fix:
- ✏️ `frontend/src/components/TaskProgressBar.vue` - Hide empty thumbnails

### Full Implementation (TODO):
- 📝 `sandbox/app/api/vnc.py` - Screenshot endpoint
- 📝 `backend/app/domain/services/agents/base.py` - Capture logic
- 📝 `backend/app/infrastructure/external/sandbox/docker_sandbox.py` - API client
- 📝 `sandbox/Dockerfile` - Install scrot
- 📝 `sandbox/app/api/router.py` - Register VNC router

---

## Current Status

✅ **Quick fix deployed** - "No preview" placeholder removed

🔧 **Proper fix pending** - Desktop screenshot capture system needs implementation

Users can now click the "Monitor" icon to view full VNC when needed, without confusing empty thumbnails.
