# Browser Resource Blocking Guide

## Overview

The Pythinker browser has configurable resource blocking to improve performance and reduce network usage. However, overly aggressive blocking can cause legitimate resources (CSS, fonts, images) to fail loading.

## How It Works

### Two-Tier Blocking System

1. **Always Blocked** (regardless of settings):
   - Ad networks (doubleclick, googlesyndication, etc.)
   - Analytics scripts (google-analytics, mixpanel, etc.)
   - Tracking pixels (facebook.com/tr, etc.)

2. **Conditionally Blocked** (when `block_resources=True`):
   - Images (`image`)
   - Fonts (`font`)
   - Stylesheets (`stylesheet`)
   - Media (`media`)

### Current Issue

If `block_resources=True` is enabled, **all stylesheets, fonts, and images are blocked**, causing pages like GitHub to appear broken with `net::ERR_FAILED` errors in the console.

## Configuration Options

### Option 1: Disable Resource Blocking Globally

**Backend Settings** (`backend/app/core/config.py`):

```python
class Settings(BaseSettings):
    # Add this field
    browser_block_resources_default: bool = Field(
        default=False,
        description="Default resource blocking for browser instances"
    )
```

**Environment Variable** (`.env`):

```env
BROWSER_BLOCK_RESOURCES_DEFAULT=false
```

### Option 2: Selective Resource Blocking

Instead of blocking all resource types, block only heavy resources (images/media) while allowing critical resources (stylesheets/fonts):

**Backend Settings** (`backend/app/core/config.py`):

```python
class Settings(BaseSettings):
    browser_blocked_resource_types: set[str] = Field(
        default={"image", "media"},  # Only block images/media, NOT stylesheets/fonts
        description="Resource types to block when blocking is enabled"
    )
```

**Environment Variable** (`.env`):

```env
# Comma-separated list of resource types to block
BROWSER_BLOCKED_RESOURCE_TYPES=image,media
```

### Option 3: Per-Session Control

Allow users to toggle resource blocking on a per-session basis via frontend UI.

## Recommended Configuration

For most use cases:

```env
# Disable global resource blocking (ads/trackers still blocked)
BROWSER_BLOCK_RESOURCES_DEFAULT=false

# If you need blocking, only block heavy resources
BROWSER_BLOCKED_RESOURCE_TYPES=image,media
```

## Performance vs Compatibility Trade-offs

| Configuration | Performance | Compatibility | Use Case |
|--------------|-------------|---------------|----------|
| `block_resources=false` | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | General browsing, research, debugging |
| Block `image,media` only | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Performance-focused browsing |
| Block `image,media,font,stylesheet` | ⭐⭐⭐⭐⭐ | ⭐ | Text-only extraction (not recommended) |

## Implementation Plan

See `BROWSER_RESOURCE_BLOCKING_FIX.md` for the implementation plan to add these configuration options.
