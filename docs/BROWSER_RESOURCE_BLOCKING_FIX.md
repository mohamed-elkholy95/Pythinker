# Browser Resource Blocking Fix - Implementation Plan

## Problem Statement

Users reported `net::ERR_FAILED` errors for legitimate resources (CSS, fonts, images) on GitHub and other sites. Investigation reveals that when `block_resources=True`, the browser blocks ALL stylesheets, fonts, images, and media - causing pages to appear broken.

## Root Cause

**File:** `backend/app/infrastructure/external/browser/playwright_browser.py`

**Line 819-821:**
```python
# Only block resource types when explicitly enabled
if self.block_resources and resource_type in self.blocked_types:
    await route.abort()
    return
```

**Current blocked types:**
```python
BLOCKABLE_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
```

When `block_resources=True`, this blocks **all** of these critical resource types, breaking page rendering.

## Solution

### Phase 1: Add Configuration Settings (Priority: P0)

**1.1. Update Settings** (`backend/app/core/config.py`)

```python
class Settings(BaseSettings):
    # Browser resource blocking
    browser_block_resources_default: bool = Field(
        default=False,
        description="Enable resource blocking by default (ads/trackers always blocked)"
    )

    browser_blocked_resource_types: str = Field(
        default="image,media",
        description="Comma-separated list of resource types to block (image,media,font,stylesheet)"
    )

    @computed_field
    @property
    def browser_blocked_types_set(self) -> set[str]:
        """Parse blocked resource types into a set"""
        if not self.browser_blocked_resource_types:
            return set()
        return {t.strip() for t in self.browser_blocked_resource_types.split(",") if t.strip()}
```

**1.2. Update Environment Variables** (`.env.example`)

```env
# Browser Resource Blocking (leave unset or false to allow all resources)
BROWSER_BLOCK_RESOURCES_DEFAULT=false

# Resource types to block when blocking is enabled (comma-separated)
# Options: image, media, font, stylesheet
# Recommended: image,media (blocks heavy resources but allows CSS/fonts)
BROWSER_BLOCKED_RESOURCE_TYPES=image,media
```

### Phase 2: Update Browser Initialization (Priority: P0)

**2.1. Update PlaywrightBrowser** (`backend/app/infrastructure/external/browser/playwright_browser.py`)

**Change line 183:**
```python
# OLD:
self.blocked_types = blocked_types or BLOCKABLE_RESOURCE_TYPES if block_resources else set()

# NEW:
settings = get_settings()
default_types = settings.browser_blocked_types_set
self.blocked_types = blocked_types or default_types if block_resources else set()
```

**2.2. Update Connection Pool** (`backend/app/infrastructure/external/browser/connection_pool.py`)

**Change line 248-249:**
```python
# OLD:
async def acquire(
    self,
    cdp_url: str,
    block_resources: bool = False,  # Hardcoded default
    ...

# NEW:
async def acquire(
    self,
    cdp_url: str,
    block_resources: bool | None = None,  # None = use settings default
    ...
):
    settings = get_settings()
    if block_resources is None:
        block_resources = settings.browser_block_resources_default
```

### Phase 3: Add Frontend Control (Priority: P1)

**3.1. Add Toggle to Settings UI** (`frontend/src/components/SettingsModal.vue`)

```vue
<FormField>
  <template #label>Browser Resource Blocking</template>
  <template #description>
    Block heavy resources (images/media) for faster browsing.
    Ads and trackers are always blocked.
  </template>
  <Switch
    v-model="settings.blockResources"
    label="Enable Resource Blocking"
  />
</FormField>
```

**3.2. Add to Session Settings API** (`backend/app/interfaces/api/v1/sessions.py`)

```python
class SessionSettings(BaseModel):
    block_resources: bool | None = None
    blocked_resource_types: set[str] | None = None
```

### Phase 4: Documentation (Priority: P1)

- ✅ Created `BROWSER_RESOURCE_BLOCKING_GUIDE.md`
- [ ] Update `CLAUDE.md` with blocking configuration
- [ ] Add troubleshooting section to `docs/guides/BROWSER_TROUBLESHOOTING.md`

## Quick Fix for Immediate Relief

If users need immediate relief, they can:

**Option 1: Restart with fresh browser instance**
```bash
# Force clear all browser connections
docker exec pythinker-backend-1 python3 -c "
from app.infrastructure.external.browser.connection_pool import BrowserConnectionPool
import asyncio

async def clear():
    pool = BrowserConnectionPool.get_instance()
    for cdp_url in list(pool._pools.keys()):
        await pool.close_all_for_url(cdp_url)
    print('All browser connections cleared')

asyncio.run(clear())
"

# Restart sandbox
docker restart pythinker-sandbox-1
```

**Option 2: Disable blocking via environment variable**
```bash
# Add to .env
echo "BROWSER_BLOCK_RESOURCES_DEFAULT=false" >> .env

# Restart backend
docker restart pythinker-backend-1
```

## Testing Plan

1. **Test default behavior** - Verify resources load correctly with default config
2. **Test selective blocking** - Verify `BROWSER_BLOCKED_RESOURCE_TYPES=image,media` blocks only images/media
3. **Test full blocking** - Verify `stylesheet,font,image,media` blocks all (for text extraction use cases)
4. **Test GitHub** - Navigate to `https://github.com` and verify CSS/fonts load correctly
5. **Test ads blocked** - Verify ad networks are still blocked regardless of resource blocking setting

## Expected Impact

- ✅ Fixes broken rendering on GitHub, developer docs, and other sites
- ✅ Maintains ad/tracker blocking (always active)
- ✅ Allows users to control performance vs compatibility trade-off
- ✅ Provides sensible defaults (block only images/media, allow CSS/fonts)

## Implementation Sequence

1. Phase 1 (Settings) - 15 minutes
2. Phase 2 (Browser init) - 15 minutes
3. Testing - 15 minutes
4. Phase 3 (Frontend) - 30 minutes (optional, can defer to later)
5. Documentation - 15 minutes

**Total: ~1.5 hours for full implementation**

## Next Steps

Would you like me to implement these fixes now? I can start with the quick fix (Option 2) to immediately resolve the issue, then implement the full solution for long-term configurability.
