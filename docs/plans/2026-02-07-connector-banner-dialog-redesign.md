# Connector Banner & Dialog Redesign

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the connector banner to show real app logos instead of colored dots, fix the ConnectorsDialog missing import + debug overlay, and align both components visually with the reference screenshots.

**Architecture:** The existing connector system (backend API, composables, dialog, cards) is fully functional. This plan is purely frontend cosmetic — no backend changes needed. We fix 3 bugs (missing import, debug overlay, unused variable) and redesign the banner to match the reference UI.

**Tech Stack:** Vue 3 (Composition API), TypeScript, lucide-vue-next, CSS scoped styles

---

### Task 1: Remove debug overlay from ConnectorsDialog

**Files:**
- Modify: `frontend/src/components/connectors/ConnectorsDialog.vue:2-5`

**Step 1: Remove the debug div**

Delete lines 2-5 (the fixed red debug indicator) from the template:

```vue
<!-- DELETE THIS -->
<div style="position: fixed; bottom: 10px; right: 10px; z-index: 99999; background: #ef4444; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; pointer-events: none;">
    ConnectorsDialog mounted | open: {{ isConnectorDialogOpen }}
</div>
```

So the template starts directly with `<Dialog ...>`.

**Step 2: Wrap template in a single root**

Since removing the debug div, the `<Dialog>` becomes the sole root element — no wrapper `<template>` change needed. Just delete lines 2-5.

**Step 3: Verify**

Run: `cd frontend && bun run type-check`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/connectors/ConnectorsDialog.vue
git commit -m "fix: remove debug overlay from ConnectorsDialog"
```

---

### Task 2: Fix missing ConnectorsDialog import in ChatPage.vue

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:314-315` (imports area)

**Step 1: Add ConnectorsDialog import**

After line 314 (`import ConnectorBanner`), add:

```typescript
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
```

**Step 2: Remove unused connectorDialogOpen variable**

In the setup section (line 327), the destructured `isConnectorDialogOpen: connectorDialogOpen` is unused. Remove it or keep it — the ConnectorsDialog manages its own visibility via the composable. Change line 327 from:

```typescript
const { isConnectorDialogOpen: connectorDialogOpen } = useConnectorDialog()
```

to just:

```typescript
useConnectorDialog()
```

(The composable still needs to be called to ensure the reactive state is initialized, but the variable is unused in ChatPage.)

**Step 3: Verify**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "fix: add missing ConnectorsDialog import in ChatPage"
```

---

### Task 3: Redesign ConnectorBanner to show app logos

The current banner shows 5 colored dots. The reference screenshot shows:
- Left: Cable icon + "Connect your tools to Pythinker" text
- Right: Row of circular app logo icons (Chrome/Globe, Gmail, Outlook, Google Drive, Slack, GitHub, Notion) + X close button
- Dark background with subtle border
- Logos are ~24px circular icons with the brand color

**Files:**
- Modify: `frontend/src/components/connectors/ConnectorBanner.vue` (full rewrite)

**Step 1: Rewrite ConnectorBanner template**

Replace the entire template with:

```vue
<template>
  <div v-if="showBanner" class="connector-banner" @click="openConnectorDialog()">
    <div class="connector-banner-left">
      <Cable :size="16" class="connector-banner-icon" />
      <span class="connector-banner-text">{{ t('Connect your tools to Pythinker') }}</span>
    </div>
    <div class="connector-banner-right">
      <div class="connector-banner-logos">
        <div
          v-for="app in previewApps"
          :key="app.id"
          class="connector-banner-logo"
          :style="{ backgroundColor: app.color + '20', color: app.color }"
        >
          <component :is="app.icon" :size="14" />
        </div>
      </div>
      <button class="connector-banner-close" @click.stop="dismissBanner">
        <X :size="14" />
      </button>
    </div>
  </div>
</template>
```

**Step 2: Rewrite the script**

Replace the script section with:

```vue
<script setup lang="ts">
import { computed, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  Cable,
  X,
  Globe,
  Mail,
  Calendar,
  HardDrive,
  MessageSquare,
  BookOpen,
} from 'lucide-vue-next';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useConnectors } from '@/composables/useConnectors';

const { t } = useI18n();
const { openConnectorDialog } = useConnectorDialog();
const { connectedCount, bannerDismissed, dismissBanner } = useConnectors();

const showBanner = computed(() => connectedCount.value === 0 && !bannerDismissed.value);

interface PreviewApp {
  id: string;
  icon: Component;
  color: string;
}

const previewApps: PreviewApp[] = [
  { id: 'browser', icon: Globe, color: '#3b82f6' },
  { id: 'gmail', icon: Mail, color: '#ea4335' },
  { id: 'outlook', icon: Mail, color: '#0078d4' },
  { id: 'drive', icon: HardDrive, color: '#34a853' },
  { id: 'slack', icon: MessageSquare, color: '#4a154b' },
  { id: 'github', icon: BookOpen, color: '#24292f' },
  { id: 'notion', icon: Calendar, color: '#000000' },
];
</script>
```

**Step 3: Rewrite the styles**

Replace the entire `<style scoped>` with:

```css
<style scoped>
.connector-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  cursor: pointer;
  transition: all 0.15s ease;
  margin-bottom: 8px;
}

.connector-banner:hover {
  border-color: var(--border-dark);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.connector-banner-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.connector-banner-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connector-banner-text {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.connector-banner-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.connector-banner-logos {
  display: flex;
  gap: 4px;
  align-items: center;
}

.connector-banner-logo {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.connector-banner-close {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.connector-banner-close:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}
</style>
```

**Step 4: Verify**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/connectors/ConnectorBanner.vue
git commit -m "feat: redesign ConnectorBanner with app logos instead of dots"
```

---

### Task 4: Polish ConnectorsDialog header/search layout

The reference screenshot shows:
- "Connectors" title with X close button at top-right (handled by DialogContent)
- Tab bar: "Apps | Custom API | Custom MCP" on the left, "Search" input on the right — **on the same row**
- Search placeholder is just "Search" (not "Search connectors...")

**Files:**
- Modify: `frontend/src/components/connectors/ConnectorsDialog.vue`

**Step 1: Move search into the tab bar row**

Replace the header + tabs sections (lines 15-42) with a combined layout:

```vue
<!-- Header: just title (close is handled by DialogContent) -->
<div class="connectors-header">
  <h2 class="connectors-title">{{ t('Connectors') }}</h2>
</div>

<!-- Tab bar + search on same row -->
<div class="connectors-tabs-row">
  <div class="connectors-tabs">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      class="connectors-tab"
      :class="{ 'connectors-tab--active': activeTab === tab.id }"
      @click="activeTab = tab.id"
    >
      {{ tab.label }}
    </button>
  </div>
  <div v-if="activeTab === 'apps'" class="connectors-search">
    <Search :size="14" class="connectors-search-icon" />
    <input
      ref="searchInputRef"
      v-model="searchQuery"
      type="text"
      class="connectors-search-input"
      :placeholder="t('Search')"
    />
  </div>
</div>
```

**Step 2: Update styles for the new layout**

Remove `.connectors-header-right` styles. Add new `.connectors-tabs-row`:

```css
.connectors-header {
  padding: 20px 24px 0;
}

.connectors-tabs-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 12px 24px 0;
  border-bottom: 1px solid var(--border-main);
}

.connectors-tabs {
  display: flex;
  gap: 0;
}
```

Remove the old `padding` and `border-bottom` from `.connectors-tabs` (now on `.connectors-tabs-row`).

**Step 3: Verify**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/connectors/ConnectorsDialog.vue
git commit -m "feat: move search into tab row and clean up dialog header"
```

---

### Task 5: Visual polish pass — connector card and dialog refinements

Small alignment tweaks to match the reference screenshots.

**Files:**
- Modify: `frontend/src/components/connectors/ConnectorCard.vue` (styles only)
- Modify: `frontend/src/components/connectors/ConnectorsDialog.vue` (styles only)

**Step 1: Update ConnectorCard icon size**

In the reference, the icons are slightly larger (~24px) in bigger colored circles (~44px). Update `.connector-card-icon`:

```css
.connector-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
```

And update the `<component>` in the template from `:size="20"` to `:size="24"`.

**Step 2: Update grid gap in ConnectorsDialog**

```css
.connectors-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
```

**Step 3: Verify**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/connectors/ConnectorCard.vue frontend/src/components/connectors/ConnectorsDialog.vue
git commit -m "style: polish connector card icons and grid spacing"
```

---

### Task 6: Final verification

**Step 1: Full frontend checks**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: PASS with 0 errors

**Step 2: Backend tests (sanity check)**

Run: `source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && cd backend && pytest tests/ -q --timeout=30`
Expected: 1920+ pass, 0 fail (no backend changes in this plan)

**Step 3: Visual review**

Start dev server: `cd frontend && bun run dev`
- Open http://localhost:5174
- Verify: ConnectorBanner shows below chatbox with app logo circles on the right
- Click banner → ConnectorsDialog opens with tabs + search on same row
- No red debug overlay visible
- Cards show 44px icon circles with 24px icons
- Search placeholder says "Search"
- X button on banner dismisses it (persisted in localStorage)

**Step 4: Final commit**

If any tweaks were needed during visual review, commit them now.
