# VNC Screenshot Implementation - Architecture & Best Practices

## Overview

This document describes the standardized implementation of VNC desktop screenshot capture for Pythinker's thumbnail preview system. The implementation follows Domain-Driven Design (DDD) principles and provides a clean abstraction layer for screenshot functionality.

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentTaskRunner                          │
│  - Orchestrates agent workflow                              │
│  - Emits tool events with screenshots                       │
└───────────────────┬─────────────────────────────────────────┘
                    │ uses
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                  ScreenshotService                          │
│  - Captures VNC desktop screenshots                         │
│  - Handles fallback to browser screenshots                  │
│  - Manages upload to file storage                           │
└───────────────────┬─────────────────────────────────────────┘
                    │ delegates to
         ┌──────────┴──────────┐
         ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│  Sandbox (VNC)  │   │     Browser     │
│  - X11 capture  │   │  - Page screenshot│
│  - xwd + convert│   │  - Fallback only│
└─────────────────┘   └─────────────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │   File Storage      │
         │   - GridFS upload   │
         │   - Returns file_id │
         └─────────────────────┘
```

## File Structure

```
backend/app/
├── domain/
│   └── services/
│       └── screenshot_service.py       # Screenshot capture service
│       └── agent_task_runner.py        # Uses screenshot service
├── core/
│   └── config.py                       # VNC screenshot config
└── infrastructure/
    └── external/
        └── sandbox/
            └── docker_sandbox.py       # VNC screenshot API client

sandbox/app/
└── api/
    └── v1/
        └── vnc.py                      # VNC screenshot endpoint
```

## Core Components

### 1. ScreenshotService (`backend/app/domain/services/screenshot_service.py`)

**Purpose**: Unified interface for capturing screenshots

**Responsibilities**:
- Capture VNC desktop screenshots via sandbox API
- Fallback to browser screenshots if VNC fails
- Upload screenshots to file storage
- Manage screenshot configuration

**Key Methods**:
- `capture_desktop_screenshot()` - Main entry point, returns file_id or None
- `_capture_vnc_screenshot()` - VNC desktop capture (primary method)
- `_capture_browser_fallback()` - Browser-only capture (fallback)

**Configuration** (`ScreenshotConfig`):
```python
quality: int = 75         # JPEG quality (1-100)
scale: float = 0.5        # Scale factor (0.1-1.0)
format: str = "jpeg"      # Image format (jpeg or png)
timeout: float = 5.0      # Timeout in seconds
```

### 2. Sandbox VNC API (`sandbox/app/api/v1/vnc.py`)

**Endpoint**: `GET /api/v1/vnc/screenshot`

**Query Parameters**:
- `quality`: JPEG quality (1-100, default 75)
- `scale`: Scale factor (0.1-1.0, default 0.5)
- `format`: Image format (jpeg or png, default jpeg)

**Implementation**:
```bash
DISPLAY=:1 xwd -root | convert xwd:- -scale 50% -quality 75 jpg:-
```

**Features**:
- Captures entire X11 desktop (not just browser)
- Uses ImageMagick for efficient processing
- Optimized for thumbnails (scaled & compressed)
- 5-second timeout protection

### 3. Configuration (`backend/app/core/config.py`)

**Settings**:
```python
vnc_screenshot_enabled: bool = True
vnc_screenshot_quality: int = 75
vnc_screenshot_scale: float = 0.5
vnc_screenshot_format: str = "jpeg"
vnc_screenshot_timeout: float = 5.0
```

**Environment Variables** (`.env.example`):
```bash
VNC_SCREENSHOT_ENABLED=true
VNC_SCREENSHOT_QUALITY=75
VNC_SCREENSHOT_SCALE=0.5
VNC_SCREENSHOT_FORMAT=jpeg
VNC_SCREENSHOT_TIMEOUT=5.0
```

## Usage

### In AgentTaskRunner

```python
# Initialize in __init__
settings = get_settings()
screenshot_config = ScreenshotConfig(
    quality=settings.vnc_screenshot_quality,
    scale=settings.vnc_screenshot_scale,
    format=settings.vnc_screenshot_format,
    timeout=settings.vnc_screenshot_timeout
)
self._screenshot_service = ScreenshotService(
    sandbox=sandbox,
    browser=browser,
    file_storage=file_storage,
    user_id=user_id,
    config=screenshot_config
)

# Capture screenshot when processing tool events
screenshot_id = await self._capture_screenshot()
event.tool_content = ShellToolContent(
    console=console_output,
    screenshot=screenshot_id  # Will be None if capture fails
)
```

## Tool Event Screenshot Coverage

All computer-use tools now capture VNC desktop screenshots:

| Tool | Screenshot Type | Shows |
|------|----------------|-------|
| `browser` | VNC Desktop | Browser window + desktop |
| `browser_agent` | VNC Desktop | Browser automation + UI |
| `shell` | VNC Desktop | Terminal window |
| `file` | VNC Desktop | Text editor / file manager |
| `code_executor` | VNC Desktop | Code editor / terminal |
| `search` | VNC Desktop | Browser search results |
| `mcp` | VNC Desktop | MCP tool execution |

## Data Flow

### Screenshot Capture Flow

```
1. Tool Event Completion
   └─> AgentTaskRunner._generate_tool_content()
       └─> self._capture_screenshot()
           └─> ScreenshotService.capture_desktop_screenshot()
               ├─> Try: _capture_vnc_screenshot()
               │   ├─> sandbox.get_screenshot(quality, scale, format)
               │   │   └─> GET /api/v1/vnc/screenshot
               │   │       └─> xwd + ImageMagick convert
               │   │           └─> Returns JPEG bytes
               │   └─> file_storage.upload_file()
               │       └─> Returns file_id
               │
               ├─> Except: _capture_browser_fallback()
               │   ├─> browser.screenshot()
               │   └─> file_storage.upload_file()
               │
               └─> Returns: file_id or None

2. Tool Event with Screenshot
   └─> Streamed to frontend via SSE
       └─> Frontend displays thumbnail
           ├─> Collapsed view: above task progress bar
           └─> Expanded view: next to "Pythinker's computer"
```

## Error Handling

### Graceful Degradation

1. **VNC Capture Fails** → Falls back to browser screenshot
2. **Browser Fallback Fails** → Returns `None` (no screenshot)
3. **Screenshot is None** → Tool content still valid, just no thumbnail

### Logging

```python
# Debug logging for successful captures
logger.debug(f"VNC screenshot captured: file_id={file_id}, size={size} bytes")

# Warning for fallback
logger.warning(f"VNC screenshot failed: {error}, attempting browser fallback")

# Error for complete failure
logger.error(f"Both VNC and browser screenshot capture failed")
```

## Best Practices

### 1. Separation of Concerns
- ✅ Screenshot logic isolated in `ScreenshotService`
- ✅ AgentTaskRunner doesn't know about VNC details
- ✅ Clean abstraction layer

### 2. Configuration Management
- ✅ Centralized in `Settings` class
- ✅ Environment variable support
- ✅ Type-safe with Pydantic models

### 3. Error Handling
- ✅ Graceful fallback mechanism
- ✅ Never crashes on screenshot failure
- ✅ Returns `Optional[str]` for safety

### 4. Performance
- ✅ Optimized image size (50% scale by default)
- ✅ JPEG compression (75 quality)
- ✅ 5-second timeout protection
- ✅ Async/await throughout

### 5. Type Safety
- ✅ Type hints on all methods
- ✅ Pydantic models for configuration
- ✅ Optional types for nullable fields

## Testing

### Unit Tests (TODO)

```python
# test_screenshot_service.py
async def test_capture_vnc_screenshot_success()
async def test_capture_vnc_screenshot_fallback_to_browser()
async def test_capture_vnc_screenshot_complete_failure()
async def test_screenshot_config_validation()
```

### Integration Tests (TODO)

```python
# test_vnc_screenshot_api.py
async def test_vnc_screenshot_endpoint()
async def test_vnc_screenshot_with_quality_params()
async def test_vnc_screenshot_timeout()
```

## Migration Notes

### Changes from Previous Implementation

**Before**:
```python
# Scattered screenshot logic
async def _get_browser_screenshot(self) -> str:
    screenshot = await self._browser.screenshot()
    # Direct browser screenshot only
```

**After**:
```python
# Centralized service
async def _capture_screenshot(self) -> Optional[str]:
    return await self._screenshot_service.capture_desktop_screenshot()
    # VNC desktop screenshot with browser fallback
```

### Benefits

1. **Better Abstraction**: Screenshot logic is now a separate service
2. **Easier Testing**: Can mock `ScreenshotService` independently
3. **More Flexible**: Easy to add new screenshot sources
4. **Type Safe**: Returns `Optional[str]` instead of assuming success
5. **Configurable**: Screenshot quality/scale/format now configurable
6. **VNC Desktop**: Captures entire desktop, not just browser

## Future Enhancements

1. **Screenshot Caching**: Cache recent screenshots to reduce VNC calls
2. **Screenshot History**: Store multiple screenshots per tool execution
3. **Screenshot Annotations**: Add visual markers for clicked elements
4. **Video Recording**: Capture video clips instead of static screenshots
5. **Screenshot Diff**: Highlight changes between screenshots
6. **Adaptive Quality**: Adjust quality based on network conditions

## Troubleshooting

### Screenshot Not Showing

1. **Check VNC is enabled**:
   ```bash
   curl http://localhost:8080/api/v1/vnc/screenshot/test
   ```

2. **Check sandbox has xwd + convert**:
   ```bash
   docker exec pythinker-sandbox-xxx which xwd convert
   ```

3. **Check backend logs**:
   ```bash
   ./dev.sh logs backend | grep -i screenshot
   ```

4. **Verify config**:
   ```bash
   # In backend container
   python -c "from app.core.config import get_settings; s=get_settings(); print(f'VNC Screenshot: {s.vnc_screenshot_enabled}')"
   ```

### Performance Issues

1. **Reduce screenshot quality**: Set `VNC_SCREENSHOT_QUALITY=50`
2. **Reduce scale**: Set `VNC_SCREENSHOT_SCALE=0.3` (30%)
3. **Disable screenshots**: Set `VNC_SCREENSHOT_ENABLED=false`

## References

- [X11 xwd documentation](https://www.x.org/releases/X11R7.6/doc/man/man1/xwd.1.xhtml)
- [ImageMagick convert](https://imagemagick.org/script/convert.php)
- [Pydantic BaseSettings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [FastAPI Response](https://fastapi.tiangolo.com/advanced/custom-response/)
