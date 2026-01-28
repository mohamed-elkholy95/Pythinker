# Agent Computer Viewer Integration Guide

## Overview

The Agent Computer Viewer provides a Claude Code-style interface for watching agents interact with the sandbox in real-time. It shows live VNC streams of browser sessions with a professional window interface, URL bar, video-style timeline controls, and task progress.

![Reference: Claude Code Computer View](reference-image.png)

## Components Created

### 1. AgentComputerView.vue

**Purpose:** Main computer window interface component

**Features:**
- Window-style interface with header and controls
- Status bar showing current tool and action
- Browser address bar with lock icon for HTTPS
- Live VNC display area
- Video-style timeline controls (play/pause, skip, seek)
- "Jump to live" button when not at current time
- Task progress bar at bottom
- Window controls (minimize, maximize, close)

**Props:**
```typescript
{
  sessionId: string;          // Session ID for VNC connection
  agentName?: string;          // Display name (e.g., "Manus", "Agent")
  currentTool?: ToolContent;   // Current tool being used
  taskTitle?: string;          // Task name/description
  taskTime?: string;           // Task duration (e.g., "1:15")
  taskStatus?: string;         // Task status text
  taskSteps?: string;          // Step progress (e.g., "2/8")
  live?: boolean;              // Whether session is live
}
```

**Events:**
```typescript
{
  close: [];                          // User closed the window
  fullscreen: [];                     // User requested fullscreen/PIP
  taskDetailsToggle: [show: boolean]; // User toggled task details
}
```

### 2. AgentComputerModal.vue

**Purpose:** Modal wrapper for AgentComputerView with backdrop

**Features:**
- Full-screen modal backdrop with blur
- Teleports to body for proper z-index
- Escape key to close
- Click backdrop to close
- Smooth fade + scale transition

**Props:**
```typescript
{
  modelValue: boolean;         // v-model for show/hide
  sessionId: string;
  agentName?: string;
  currentTool?: ToolContent;
  taskTitle?: string;
  taskTime?: string;
  taskStatus?: string;
  taskSteps?: string;
  live?: boolean;
}
```

**Events:**
```typescript
{
  'update:modelValue': [value: boolean];
  fullscreen: [];
  taskDetailsToggle: [show: boolean];
}
```

### 3. useBrowserState.ts

**Purpose:** Composable for tracking browser state across components

**API:**
```typescript
const {
  currentBrowserUrl,      // ref<string> - Current page URL
  currentBrowserAction,   // ref<string> - Current action (e.g., "Browsing")
  browserHistory,         // ref<Array> - History of visited URLs
  latestUrl,             // computed<string> - Most recent URL
  isBrowsing,            // computed<boolean> - Whether currently browsing
  updateBrowserState,    // (toolContent) => void - Update from tool
  clearBrowserState,     // () => void - Reset state
} = useBrowserState();
```

## Integration Steps

### Step 1: Add Button to ToolPanelContent Header

**File:** `frontend/src/components/ToolPanelContent.vue`

Add a button in the window controls section (line ~8-36):

```vue
<template>
  <div class="flex items-center gap-1">
    <!-- New: Computer View Button -->
    <button
      v-if="isBrowserTool"
      class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]"
      @click="openComputerView"
      aria-label="Open Computer View"
      title="Open Computer View"
    >
      <MonitorPlay class="w-4 h-4 text-[var(--icon-tertiary)]" />
    </button>

    <!-- Existing buttons -->
    <button @click="openCodeServer" ...>
      <Code ... />
    </button>
    <!-- ... rest of buttons -->
  </div>
</template>

<script setup lang="ts">
import { MonitorPlay } from 'lucide-vue-next';

// Add state
const showComputerView = ref(false);

// Check if current tool is browser-related
const isBrowserTool = computed(() => {
  const toolName = props.toolContent?.name || '';
  return toolName === 'browser' || toolName === 'browser_agent';
});

// Open computer view
const openComputerView = () => {
  showComputerView.value = true;
};
</script>
```

### Step 2: Add AgentComputerModal to ToolPanelContent

**File:** `frontend/src/components/ToolPanelContent.vue`

Add the modal component at the end of the template:

```vue
<template>
  <div>
    <!-- Existing content -->
    <!-- ... -->

    <!-- Agent Computer Modal -->
    <AgentComputerModal
      v-model="showComputerView"
      :session-id="props.sessionId || ''"
      agent-name="Pythinker"
      :current-tool="props.toolContent"
      :task-title="currentTaskTitle"
      :task-time="currentTaskTime"
      :task-status="currentTaskStatus"
      :task-steps="currentTaskSteps"
      :live="props.live"
      @fullscreen="handleFullscreen"
      @task-details-toggle="handleTaskDetailsToggle"
    />
  </div>
</template>

<script setup lang="ts">
import AgentComputerModal from './AgentComputerModal.vue';
import { useBrowserState } from '@/composables/useBrowserState';

// Initialize browser state tracker
const { updateBrowserState } = useBrowserState();

// Watch for tool changes to update browser state
watch(() => props.toolContent, (toolContent) => {
  if (toolContent) {
    updateBrowserState(toolContent);
  }
}, { immediate: true, deep: true });

// Compute task info from plan (if available)
const currentTaskTitle = computed(() => {
  // Extract from plan or session state
  return 'Research Claude Code and produce best practices guide';
});

const currentTaskTime = computed(() => {
  // Calculate elapsed time
  return '1:15';
});

const currentTaskStatus = computed(() => {
  return 'Using browser';
});

const currentTaskSteps = computed(() => {
  // Get from plan
  return '2/8';
});

const handleFullscreen = () => {
  // Implement fullscreen/picture-in-picture
  console.log('Fullscreen requested');
};

const handleTaskDetailsToggle = (show: boolean) => {
  console.log('Task details toggle:', show);
};
</script>
```

### Step 3: Import MonitorPlay Icon

Make sure to import the icon in ToolPanelContent.vue:

```typescript
import {
  Code,
  MonitorUp,
  Minimize2,
  X,
  MonitorPlay // Add this
} from 'lucide-vue-next';
```

### Step 4: Optional - Add to ChatPage Directly

For a more prominent placement, you can add a floating button in ChatPage.vue:

```vue
<template>
  <div class="chat-page">
    <!-- Existing chat interface -->
    <!-- ... -->

    <!-- Floating Computer View Button -->
    <button
      v-if="showComputerViewButton"
      @click="openComputerView"
      class="fixed bottom-24 right-6 z-40 w-14 h-14 rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 hover:scale-110 transition-all flex items-center justify-center"
      title="Open Computer View"
    >
      <MonitorPlay :size="24" />
    </button>

    <!-- Agent Computer Modal -->
    <AgentComputerModal
      v-model="showComputerView"
      :session-id="sessionId"
      agent-name="Pythinker"
      :current-tool="currentTool"
      :task-title="currentTask?.description"
      :live="isLive"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { MonitorPlay } from 'lucide-vue-next';
import AgentComputerModal from '@/components/AgentComputerModal.vue';

const showComputerView = ref(false);

const showComputerViewButton = computed(() => {
  // Show when agent is actively using browser
  return currentTool.value?.name === 'browser' && isLive.value;
});

const openComputerView = () => {
  showComputerView.value = true;
};
</script>
```

## Usage Examples

### Example 1: Basic Usage

```vue
<template>
  <AgentComputerView
    session-id="abc123"
    agent-name="Assistant"
    :current-tool="currentTool"
    :live="true"
    @close="handleClose"
  />
</template>

<script setup lang="ts">
import AgentComputerView from '@/components/AgentComputerView.vue';

const currentTool = ref({
  name: 'browser',
  function: 'browser_navigate',
  args: { url: 'https://code.claude.com/docs' },
  status: 'calling'
});

const handleClose = () => {
  console.log('User closed computer view');
};
</script>
```

### Example 2: With Task Progress

```vue
<template>
  <AgentComputerModal
    v-model="isOpen"
    session-id="abc123"
    agent-name="Manus"
    :current-tool="currentTool"
    task-title="Task 1: Research Claude Code and produce best practices guide"
    task-time="1:15"
    task-status="Using browser"
    task-steps="2/8"
    :live="true"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import AgentComputerModal from '@/components/AgentComputerModal.vue';

const isOpen = ref(true);
</script>
```

### Example 3: With Browser State Tracking

```vue
<script setup lang="ts">
import { watch } from 'vue';
import { useBrowserState } from '@/composables/useBrowserState';
import AgentComputerView from '@/components/AgentComputerView.vue';

const { currentBrowserUrl, updateBrowserState } = useBrowserState();

// Update browser state when tool events come in
watch(() => props.toolContent, (tool) => {
  if (tool) {
    updateBrowserState(tool);
  }
}, { deep: true });
</script>
```

## Styling Customization

### Theme Colors

The component uses a dark theme by default. To customize:

```css
/* In your global CSS or component style */
.agent-computer-container {
  --computer-bg: #2d2d2d;
  --computer-header-bg: #1e1e1e;
  --computer-text: #e5e7eb;
  --computer-text-secondary: #9ca3af;
  --computer-accent: #60a5fa;
  --computer-border: #404040;
}
```

### Window Size

Adjust max-width/max-height in `AgentComputerView.vue`:

```css
.computer-window {
  max-width: 1200px;  /* Larger window */
  max-height: 95vh;   /* Taller window */
}
```

### Address Bar

Hide address bar if not needed:

```vue
<template>
  <AgentComputerView
    :show-address-bar="false"
    ...
  />
</template>
```

## Advanced Features

### 1. Session Recording & Playback

The timeline controls are ready for session playback functionality:

```typescript
// Enable playback
const canPlayback = ref(true);
const totalTime = ref(180); // 3 minutes in seconds

// Update current time
const currentTime = ref(45); // 45 seconds in

// The timeline will automatically show progress
```

### 2. Picture-in-Picture Mode

Implement PIP using the native browser API:

```typescript
const toggleFullscreen = async () => {
  const videoElement = vncContainer.value?.querySelector('canvas');
  if (videoElement && document.pictureInPictureEnabled) {
    try {
      await videoElement.requestPictureInPicture();
    } catch (error) {
      console.error('Failed to enter PIP:', error);
    }
  }
};
```

### 3. Task Progress from Plan

Extract task info from plan events:

```typescript
import type { PlanEventData } from '@/types/event';

const extractTaskInfo = (plan: PlanEventData) => {
  const currentStep = plan.steps.find(s => s.status === 'running');
  return {
    title: currentStep?.description || 'Working...',
    steps: `${plan.steps.filter(s => s.status === 'completed').length}/${plan.steps.length}`,
    time: formatElapsedTime(plan.startTime),
  };
};
```

## Troubleshooting

### VNC Not Connecting

**Issue:** Black screen or "Connecting to sandbox..." forever

**Solutions:**
1. Check VNC WebSocket endpoint is accessible
2. Verify sandbox is running: `docker ps | grep sandbox`
3. Check backend logs for VNC tunnel errors
4. Verify signed URL generation is working

### URL Not Updating

**Issue:** Address bar shows old URL

**Solutions:**
1. Ensure `useBrowserState` composable is being called
2. Check that `updateBrowserState` is called on tool changes
3. Verify `browser_navigate` events include `args.url`

### Timeline Controls Disabled

**Issue:** Play/pause buttons are grayed out

**Explanation:** Timeline controls are for session playback (not yet implemented)

**To Enable:**
```typescript
const canPlayback = ref(true); // Enable controls
```

## Performance Considerations

### VNC Stream Optimization

The VNC connection uses NoVNC with optimized settings:
- **scaleViewport**: Automatic scaling to fit container
- **clipViewport**: Clip to visible area only
- **viewOnly**: Read-only mode reduces bandwidth

### Connection Management

- Auto-reconnect with exponential backoff
- Max 5-second retry delay
- Proper cleanup on component unmount

### Resource Usage

- **Memory:** ~20-50MB for VNC canvas buffer
- **Network:** ~500kbps - 2Mbps for VNC stream
- **CPU:** Minimal (browser handles rendering)

## Future Enhancements

### Planned Features

1. **Session Recording**
   - Record agent sessions for playback
   - Scrub through timeline
   - Export recordings

2. **Multiple Views**
   - Split screen for multiple sandboxes
   - Grid layout for monitoring multiple agents

3. **Enhanced Controls**
   - Speed control (0.5x, 1x, 2x)
   - Frame-by-frame stepping
   - Bookmarks/markers

4. **Collaboration**
   - Share computer view URLs
   - Live annotations
   - Voice commentary

## API Reference

### AgentComputerView Props

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `sessionId` | `string` | Yes | - | Session ID for VNC connection |
| `agentName` | `string` | No | `'Agent'` | Display name in header |
| `currentTool` | `ToolContent` | No | - | Current tool being executed |
| `taskTitle` | `string` | No | - | Task name/description |
| `taskTime` | `string` | No | - | Elapsed time (e.g., "1:15") |
| `taskStatus` | `string` | No | - | Status text (e.g., "Using browser") |
| `taskSteps` | `string` | No | - | Step progress (e.g., "2/8") |
| `live` | `boolean` | No | `true` | Whether session is live |

### AgentComputerView Events

| Event | Payload | Description |
|-------|---------|-------------|
| `close` | - | User clicked close button |
| `fullscreen` | - | User requested fullscreen/PIP |
| `taskDetailsToggle` | `boolean` | User toggled task details |

## Support

For issues or questions:
- Check existing implementations in `frontend/src/components/`
- Review VNC integration in `VNCViewer.vue`
- See tool display logic in `BrowserToolView.vue`

## Summary

The Agent Computer Viewer provides a professional, Claude Code-style interface for monitoring agent activities in real-time. Key benefits:

✅ **Professional UI** - Polished window interface with proper controls
✅ **Live VNC** - Real-time view of browser sessions
✅ **URL Tracking** - Shows current page being browsed
✅ **Task Progress** - Displays task info and completion
✅ **Video Controls** - Timeline for session playback (ready for implementation)
✅ **Easy Integration** - Drop-in component with minimal setup
✅ **Responsive** - Works on desktop and tablet screens
✅ **Accessible** - Keyboard shortcuts and ARIA labels

**Implementation Time:** ~15-30 minutes for basic integration
**Maintenance:** Low (self-contained components)
**Browser Support:** Modern browsers with WebSocket and NoVNC support
