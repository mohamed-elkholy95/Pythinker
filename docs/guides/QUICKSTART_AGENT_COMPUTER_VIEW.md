# Quick Start: Agent Computer View

Get the Claude Code-style computer viewer running in 10 minutes.

## ✨ What You'll Get

A professional computer window interface showing:
- ✅ Live VNC stream of agent's browser
- ✅ Real-time URL display in address bar
- ✅ Current tool and action status
- ✅ Task progress with time and steps
- ✅ Video-style playback controls

## 🚀 3-Step Integration

### Step 1: Add Button (2 minutes)

**File:** `frontend/src/components/ToolPanelContent.vue`

Find the window controls section (around line 8) and add this button:

```vue
<template>
  <div class="flex items-center gap-2 w-full">
    <div class="text-[var(--text-primary)] text-lg font-semibold flex-1">
      {{ $t("Pythinker's Computer") }}
    </div>
    <div class="flex items-center gap-1">
      <!-- 👇 NEW: Computer View Button -->
      <button
        v-if="isBrowserTool"
        class="w-7 h-7 rounded-md inline-flex items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]"
        @click="showComputerView = true"
        aria-label="Open Computer View"
        title="Open Computer View"
      >
        <MonitorPlay class="w-4 h-4 text-[var(--icon-tertiary)]" />
      </button>

      <!-- Existing buttons -->
      <button @click="openCodeServer" ...>
        <Code ... />
      </button>
      <!-- ... other buttons ... -->
    </div>
  </div>
</template>
```

### Step 2: Add Modal (3 minutes)

**File:** `frontend/src/components/ToolPanelContent.vue`

Add at the **end of the template** (after all existing content):

```vue
<template>
  <div class="...">
    <!-- Existing content -->
    <!-- ... all your current template code ... -->

    <!-- 👇 NEW: Agent Computer Modal -->
    <AgentComputerModal
      v-model="showComputerView"
      :session-id="props.sessionId || ''"
      agent-name="Pythinker"
      :current-tool="props.toolContent"
      :task-title="taskTitle"
      :task-time="taskTime"
      :task-status="taskStatus"
      :task-steps="taskSteps"
      :live="props.live"
    />
  </div>
</template>
```

### Step 3: Add Script Code (5 minutes)

**File:** `frontend/src/components/ToolPanelContent.vue`

Add to the `<script setup>` section:

```typescript
// 👇 NEW: Add imports at the top
import { MonitorPlay } from 'lucide-vue-next';
import AgentComputerModal from './AgentComputerModal.vue';

// 👇 NEW: Add state
const showComputerView = ref(false);

// 👇 NEW: Check if browser tool
const isBrowserTool = computed(() => {
  const toolName = props.toolContent?.name || '';
  return toolName === 'browser' || toolName === 'browser_agent';
});

// 👇 NEW: Task info (basic version)
const taskTitle = computed(() => {
  return props.toolContent?.args?.url || 'Working...';
});

const taskTime = computed(() => {
  return '0:00'; // TODO: Calculate from start time
});

const taskStatus = computed(() => {
  const actionMap: Record<string, string> = {
    browser_navigate: 'Browsing',
    browser_click: 'Clicking',
    browser_input: 'Typing',
    browser_get_content: 'Reading',
    browser_view: 'Viewing',
    shell_execute: 'Executing',
    file_write: 'Writing',
    file_read: 'Reading',
  };
  const func = props.toolContent?.function || '';
  return actionMap[func] || 'Using tool';
});

const taskSteps = computed(() => {
  return ''; // TODO: Get from plan if available
});
```

## ✅ Done!

That's it! Now when an agent uses the browser:

1. You'll see a **MonitorPlay icon** button in the header
2. Click it to open the **Agent Computer View**
3. Watch the agent browse in real-time
4. See the URL update as they navigate
5. Monitor task progress at the bottom

## 🎯 Quick Test

1. Start a chat session
2. Ask agent to browse a website: `"Search for Claude Code documentation"`
3. Click the MonitorPlay button when agent starts browsing
4. See the live computer view!

## 🔧 Troubleshooting

### Button doesn't appear

**Check:**
- Is the tool a browser tool? (`toolContent?.name === 'browser'`)
- Did you import `MonitorPlay` from lucide-vue-next?
- Is `isBrowserTool` computed property defined?

### Modal doesn't open

**Check:**
- Is `AgentComputerModal` imported correctly?
- Is `showComputerView` ref defined?
- Check browser console for errors

### VNC shows black screen

**Check:**
- Is sandbox running? `docker ps | grep sandbox`
- Is VNC port accessible? (5901)
- Check backend VNC tunnel logs

## 📚 Next Steps

### Add Task Progress (Optional)

For real task progress, extract from plan:

```typescript
import type { PlanEventData } from '@/types/event';

// If you have plan prop
const taskTitle = computed(() => {
  if (!plan?.value) return 'Working...';
  const currentStep = plan.value.steps.find(s => s.status === 'running');
  return currentStep?.description || 'Processing...';
});

const taskSteps = computed(() => {
  if (!plan?.value) return '';
  const completed = plan.value.steps.filter(s => s.status === 'completed').length;
  const total = plan.value.steps.length;
  return `${completed}/${total}`;
});
```

### Add Elapsed Time (Optional)

Track time since task started:

```typescript
import { ref, onMounted, onUnmounted } from 'vue';

const startTime = ref(Date.now());
const taskTime = ref('0:00');
let timeInterval: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  timeInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime.value) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    taskTime.value = `${minutes}:${seconds.toString().padStart(2, '0')}`;
  }, 1000);
});

onUnmounted(() => {
  if (timeInterval) clearInterval(timeInterval);
});
```

## 🎨 Customization

### Change Agent Name

```vue
<AgentComputerModal
  agent-name="Assistant"  <!-- or "Manus", "Agent", etc. -->
  ...
/>
```

### Hide Task Progress

```vue
<AgentComputerModal
  task-title=""  <!-- Empty to hide -->
  ...
/>
```

### Customize Window Size

Edit `AgentComputerView.vue`:

```css
.computer-window {
  max-width: 1200px;  /* Wider window */
  max-height: 95vh;   /* Taller window */
}
```

## 📖 Full Documentation

For advanced features, customization, and API details:
- **Integration Guide:** `docs/AGENT_COMPUTER_VIEWER_INTEGRATION.md`
- **Implementation Summary:** `AGENT_COMPUTER_VIEWER_IMPLEMENTATION_SUMMARY.md`

## 🎉 Enjoy!

You now have a professional Claude Code-style interface for monitoring your agents! 🚀
