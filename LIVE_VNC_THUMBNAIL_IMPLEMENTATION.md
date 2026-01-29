# Live VNC Thumbnail Implementation - Best Practices & Plan

## Research Summary

### Key Findings from Web Search

#### 1. Real-Time Image Update Best Practices
- **WebSocket Streaming**: Persistent bidirectional connection for sub-100ms updates
- **Polling Optimization**: Balance between update frequency and performance
- **Base64 Image Streaming**: Efficient for small images over WebSocket
- **Frame Rate Control**: VNC servers support configurable frame rates (RealVNC: 50ms poll interval default)

#### 2. VNC Screenshot Performance (from RealVNC docs)
```
PollInterval: 50ms (default) - milliseconds between screen polls
- Larger number = better performance, higher latency
- Smaller number = more CPU, lower latency
- Recommendation: 50-100ms for good balance
```

#### 3. Thumbnail Update Frequency Best Practices
- **Live dashboards**: 1-2 FPS (500-1000ms) sufficient for thumbnails
- **Real-time editing**: 10-20 FPS (50-100ms) for interactive feel
- **Video streaming**: 24-30 FPS (33-42ms) for smooth video

**For task progress thumbnails**: **1-2 FPS (500-1000ms)** is optimal
- Shows activity without overwhelming the UI
- Low CPU/network overhead
- Good enough to see browser navigation, terminal output

### 4. Vue 3 Reactive Image Updates
```javascript
import { ref, watchEffect } from 'vue'

// Reactive image source
const thumbnailUrl = ref('')

// Auto-updates whenever thumbnailUrl changes
watchEffect(() => {
  console.log('Thumbnail updated:', thumbnailUrl.value)
})

// Update the thumbnail (triggers re-render)
thumbnailUrl.value = 'data:image/jpeg;base64,...'
```

---

## Current Implementation Analysis

### What We Have Now
1. **Static screenshot capture** (`screenshot_service.py`):
   - Single on-demand VNC screenshot via `/api/v1/vnc/screenshot`
   - Quality: 75%, Scale: 50%, Format: JPEG
   - Stored in file storage, returns file ID

2. **TaskProgressBar.vue**:
   - Shows **single static thumbnail** from `thumbnailUrl` prop
   - Comments explicitly say "uses static screenshot, not live VNC" (lines 5, 74)
   - No auto-refresh mechanism

3. **VNC WebSocket** (`session_routes.py`):
   - Already has WebSocket tunnel for VNC viewer
   - Runs at `ws://{backend}/api/v1/sessions/{id}/vnc`
   - Used by full VNC viewer, not thumbnails

### What's Missing
- ❌ Periodic screenshot polling for thumbnails
- ❌ Auto-refresh mechanism in frontend
- ❌ Visibility detection (don't poll when thumbnail hidden)
- ❌ Configurable update interval
- ❌ Memory cleanup on component unmount

---

## Implementation Strategy

### Architecture: **Polling Approach** (Recommended)

**Why polling instead of WebSocket streaming?**
1. ✅ Simpler implementation - no new WebSocket endpoint needed
2. ✅ Reuses existing screenshot API
3. ✅ Easy to control update frequency (configurable interval)
4. ✅ No persistent connection overhead
5. ✅ Auto-stops when component unmounts
6. ✅ Works with existing thumbnail display code

**Trade-off**: Slightly higher latency (~500ms) vs WebSocket (~50ms), but acceptable for thumbnails

---

## Implementation Plan

### Phase 1: Backend - Enhance Screenshot API ✅ (Already exists!)

**Current endpoint**: `GET /api/v1/vnc/screenshot`
- Already supports quality, scale, format params
- Returns JPEG image directly
- No changes needed! 🎉

### Phase 2: Frontend - Create Vue Composable for Live Thumbnails

**File**: `frontend/src/composables/useLiveVncThumbnail.ts`

```typescript
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { getApiClient } from '@/api/client'

export interface UseLiveThumbnailOptions {
  sessionId: string
  enabled?: boolean // Control when polling is active
  interval?: number // Polling interval in ms (default: 1000)
  quality?: number // JPEG quality 1-100 (default: 50 for thumbnails)
  scale?: number // Scale factor 0.1-1.0 (default: 0.3 for small thumbnails)
}

export function useLiveVncThumbnail(options: UseLiveThumbnailOptions) {
  const thumbnailUrl = ref<string>('')
  const isLoading = ref(false)
  const error = ref<Error | null>(null)
  let intervalId: ReturnType<typeof setInterval> | null = null

  const fetchThumbnail = async () => {
    if (!options.sessionId || isLoading.value) return

    try {
      isLoading.value = true
      error.value = null

      // Fetch screenshot as blob
      const response = await getApiClient().get(
        `/sessions/${options.sessionId}/vnc/screenshot`,
        {
          params: {
            quality: options.quality ?? 50,
            scale: options.scale ?? 0.3,
            format: 'jpeg'
          },
          responseType: 'blob'
        }
      )

      // Convert blob to data URL for img src
      const blob = response.data
      const reader = new FileReader()
      reader.onloadend = () => {
        thumbnailUrl.value = reader.result as string
      }
      reader.readAsDataURL(blob)

    } catch (err) {
      error.value = err as Error
      console.warn('Failed to fetch VNC thumbnail:', err)
    } finally {
      isLoading.value = false
    }
  }

  const startPolling = () => {
    if (intervalId) return // Already polling

    // Fetch immediately
    fetchThumbnail()

    // Then poll at interval
    intervalId = setInterval(
      fetchThumbnail,
      options.interval ?? 1000 // Default: 1 FPS
    )
  }

  const stopPolling = () => {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  // Watch enabled state to start/stop polling
  watch(
    () => options.enabled,
    (enabled) => {
      if (enabled) {
        startPolling()
      } else {
        stopPolling()
      }
    },
    { immediate: true }
  )

  // Cleanup on unmount
  onUnmounted(() => {
    stopPolling()
  })

  return {
    thumbnailUrl, // Reactive ref - updates automatically
    isLoading,
    error,
    refresh: fetchThumbnail, // Manual refresh
    startPolling,
    stopPolling
  }
}
```

### Phase 3: Update TaskProgressBar to Use Live Thumbnails

**File**: `frontend/src/components/TaskProgressBar.vue`

**Changes**:

1. **Import composable** (after line 182):
```typescript
import { useLiveVncThumbnail } from '@/composables/useLiveVncThumbnail'
```

2. **Add live thumbnail logic** (after line 211):
```typescript
// Live VNC thumbnail polling
const {
  thumbnailUrl: liveThumbnailUrl,
  isLoading: thumbnailLoading
} = useLiveVncThumbnail({
  sessionId: props.sessionId,
  enabled: computed(() =>
    // Only poll when thumbnail should be visible AND task is running
    (showCollapsedThumbnail.value || showExpandedThumbnail.value) &&
    !isAllCompleted.value
  ),
  interval: 1000, // 1 FPS - smooth enough for progress feedback
  quality: 50, // Lower quality for small thumbnails
  scale: 0.3 // 30% scale for small size
})

// Use live thumbnail if available, fallback to static prop
const displayThumbnailUrl = computed(() =>
  liveThumbnailUrl.value || props.thumbnailUrl
)
```

3. **Update template to use live thumbnail** (lines 18, 81):
```vue
<!-- Replace :src="thumbnailUrl" with :src="displayThumbnailUrl" -->
<img
  :src="displayThumbnailUrl"
  alt="Screenshot"
  class="w-full h-full object-cover"
/>
```

4. **Update comments** (lines 5, 74):
```vue
<!-- Remove "uses static screenshot, not live VNC" -->
<!-- Replace with "Live VNC thumbnail (auto-updates during task execution)" -->
```

---

## Performance Optimizations

### 1. Visibility-Based Polling
```typescript
// Only poll when thumbnail is actually visible
enabled: computed(() =>
  (showCollapsedThumbnail.value || showExpandedThumbnail.value) &&
  !isAllCompleted.value
)
```

### 2. Page Visibility API (Future Enhancement)
```typescript
// Pause polling when browser tab is not active
watch(() => document.hidden, (hidden) => {
  if (hidden) stopPolling()
  else if (options.enabled) startPolling()
})
```

### 3. Configurable Quality/Scale
- **Small collapsed thumbnail**: quality=50, scale=0.3 (140x80px → ~42x24px native)
- **Large expanded thumbnail**: quality=60, scale=0.4 (140x80px → ~56x32px native)

### 4. Debouncing (Future Enhancement)
```typescript
// Skip fetch if previous one is still loading
if (isLoading.value) return
```

---

## Configuration Options

### Backend (already exists in `config.py`)
```python
vnc_screenshot_enabled: bool = True
vnc_screenshot_quality: int = 75  # Default for manual captures
vnc_screenshot_scale: float = 0.5
vnc_screenshot_format: str = "jpeg"
vnc_screenshot_timeout: float = 5.0
```

### Frontend (new - add to TaskProgressBar props)
```typescript
interface Props {
  // ... existing props
  liveVnc?: boolean // Enable live VNC thumbnails (default: true)
  liveVncInterval?: number // Update interval in ms (default: 1000)
  liveVncQuality?: number // JPEG quality 1-100 (default: 50)
}
```

---

## Testing Plan

### 1. Basic Functionality
```bash
# Start session with browsing task
# Expected: Thumbnail appears and updates ~1 time per second
```

### 2. Performance Testing
```bash
# Monitor network requests in DevTools
# Expected: ~1 request/second, ~5-10KB per image
```

### 3. Visibility Testing
```bash
# Collapse task progress bar
# Expected: Polling stops (no requests)
# Expand again
# Expected: Polling resumes
```

### 4. Completion Testing
```bash
# Wait for task to complete
# Expected: Polling stops, shows final thumbnail
```

### 5. Multi-Session Testing
```bash
# Open 2 chat sessions simultaneously
# Expected: Each has independent polling, no interference
```

---

## Rollout Strategy

### Option A: Gradual Rollout (Recommended)
1. ✅ Create composable `useLiveVncThumbnail.ts`
2. ✅ Add `liveVnc` prop to TaskProgressBar (default: `false`)
3. ✅ Test with single user setting `liveVnc={true}`
4. ✅ Monitor performance, adjust interval/quality
5. ✅ Set default to `true` for all users

### Option B: Feature Flag
```typescript
// In TaskProgressBar.vue
const ENABLE_LIVE_VNC = import.meta.env.VITE_ENABLE_LIVE_VNC === 'true'
```

---

## Alternatives Considered

### Alternative 1: WebSocket Streaming
**Pros**:
- Lower latency (~50ms vs ~500ms)
- True real-time updates
- More efficient for high-frequency updates

**Cons**:
- Requires new WebSocket endpoint
- More complex backend implementation
- Persistent connection overhead
- Harder to debug

**Verdict**: ❌ Overkill for thumbnails - polling is simpler and sufficient

### Alternative 2: Server-Sent Events (SSE)
**Pros**:
- One-way server → client (perfect for thumbnails)
- Auto-reconnection built-in
- Simpler than WebSocket

**Cons**:
- Still requires new endpoint
- Base64 encoding overhead for images
- Browser limit (6 concurrent SSE per domain)

**Verdict**: ❌ Polling is simpler for this use case

### Alternative 3: Periodic Static Screenshot Update
**Pros**:
- No continuous polling
- Uses existing file storage

**Cons**:
- Not truly "live"
- Requires backend to push updates
- Complex coordination

**Verdict**: ❌ Polling composable is cleaner

---

## Success Metrics

### Performance Targets
- ✅ Network overhead: <10KB/second per session
- ✅ CPU impact: <2% additional CPU usage
- ✅ Memory: <5MB additional per session
- ✅ Update latency: <1.5 seconds perceived delay

### User Experience Targets
- ✅ Thumbnail updates visible within 1 second
- ✅ No UI jank or freezing
- ✅ Smooth transition between thumbnails
- ✅ Graceful degradation on errors

---

## Future Enhancements

### 1. Adaptive Polling
```typescript
// Faster updates when browser navigating, slower when idle
const adaptiveInterval = computed(() => {
  if (isToolRunning.value && currentToolName.value.includes('browser')) {
    return 500 // 2 FPS during active browsing
  }
  return 2000 // 0.5 FPS during idle
})
```

### 2. Progressive JPEG
- Use progressive JPEG encoding
- Show low-quality preview immediately
- Refine as more data arrives

### 3. Thumbnail History
- Keep last 5-10 thumbnails
- Allow scrubbing through task history
- "Replay" button to see task execution

### 4. Motion Detection
- Only update thumbnail if screen changed significantly
- Compare image hashes to detect motion
- Save bandwidth during idle periods

---

## Summary

**Recommended Approach**: **Polling with Vue Composable**

**Key Benefits**:
1. ✅ Simple implementation - reuses existing screenshot API
2. ✅ Automatic cleanup - Vue lifecycle management
3. ✅ Configurable - quality, scale, interval all adjustable
4. ✅ Performant - visibility-based polling, optimized image size
5. ✅ Maintainable - clean separation of concerns

**Implementation Steps**:
1. Create `useLiveVncThumbnail.ts` composable (30 min)
2. Update `TaskProgressBar.vue` to use composable (15 min)
3. Test and tune polling interval (15 min)
4. Deploy and monitor (ongoing)

**Total Estimated Time**: 1 hour initial implementation + monitoring

---

## Next Steps

1. ✅ Review this plan
2. ✅ Create composable implementation
3. ✅ Update TaskProgressBar component
4. ✅ Test with live browsing session
5. ✅ Tune performance parameters
6. ✅ Deploy to production
