# Shared Tool View Components

This directory contains reusable, standardized components for all tool views in Pythinker.

## 📦 Components

### State Components

#### LoadingState
Displays a loading animation with label and optional detail text.

```vue
<LoadingState
  label="Fetching content"
  detail="example.com"
  animation="globe"
  :is-active="true"
/>
```

**Props:**
- `label` (string, required): Main loading message
- `detail` (string, optional): Additional detail text
- `animation` (string, optional): Animation type - 'globe', 'search', 'file', 'terminal', 'code', 'spinner'
- `isActive` (boolean, optional): Whether to show animated dots

#### EmptyState
Displays an empty state with icon and message.

```vue
<EmptyState
  message="No content available"
  icon="inbox"
>
  <template #action>
    <button @click="handleAction">Load Content</button>
  </template>
</EmptyState>
```

**Props:**
- `message` (string, required): Empty state message
- `icon` (string, optional): Icon type - 'file', 'terminal', 'search', 'browser', 'code', 'inbox'
- `overlay` (boolean, optional): Display as overlay

#### ErrorState
Displays an error message with optional retry button.

```vue
<ErrorState
  error="Failed to load content"
  :retryable="true"
  @retry="handleRetry"
/>
```

**Props:**
- `error` (string, required): Error message
- `retryable` (boolean, optional): Show retry button

**Events:**
- `retry`: Emitted when retry button is clicked

### Layout Components

#### ContentContainer
Provides consistent container with scrolling and width constraints.

```vue
<ContentContainer
  :scrollable="true"
  :centered="false"
  constrained="medium"
  padding="md"
>
  <div>Your content here</div>
</ContentContainer>
```

**Props:**
- `scrollable` (boolean, default: true): Enable scrolling
- `centered` (boolean, default: false): Center content vertically
- `constrained` (boolean | 'medium' | 'wide', default: false): Constrain width
- `padding` ('none' | 'sm' | 'md' | 'lg', default: 'md'): Padding size

### Utility Components

#### LoadingDots
Animated dots for loading states.

```vue
<span>Loading</span>
<LoadingDots />
```

## 🎬 Animations

All animation components are located in the `animations/` directory:

- **GlobeAnimation**: For browser/network operations
- **SearchAnimation**: For search operations
- **FileAnimation**: For file operations
- **TerminalAnimation**: For shell operations
- **CodeAnimation**: For code execution
- **SpinnerAnimation**: Generic loading spinner

## 📖 Usage Examples

### Basic Tool View Template

```vue
<template>
  <ContentContainer :scrollable="true">
    <!-- Loading State -->
    <LoadingState
      v-if="isLoading"
      :label="loadingLabel"
      :detail="loadingDetail"
      animation="globe"
    />

    <!-- Error State -->
    <ErrorState
      v-else-if="error"
      :error="error"
      :retryable="true"
      @retry="handleRetry"
    />

    <!-- Empty State -->
    <EmptyState
      v-else-if="isEmpty"
      message="No content available"
      icon="inbox"
    />

    <!-- Content -->
    <div v-else>
      <!-- Your content here -->
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import LoadingState from './shared/LoadingState.vue';
import EmptyState from './shared/EmptyState.vue';
import ErrorState from './shared/ErrorState.vue';
import ContentContainer from './shared/ContentContainer.vue';

const isLoading = ref(false);
const error = ref('');
const content = ref(null);

const isEmpty = computed(() => !content.value);
const loadingLabel = 'Loading content';
const loadingDetail = 'Please wait...';

const handleRetry = () => {
  // Retry logic
};
</script>
```

### Browser Tool View Example

```vue
<template>
  <ContentContainer :scrollable="false">
    <LoadingState
      v-if="isFetching"
      label="Browsing"
      :detail="url"
      animation="globe"
    />
    <LiveViewer v-else :session-id="sessionId" />
  </ContentContainer>
</template>
```

### Search Tool View Example

```vue
<template>
  <ContentContainer :centered="isSearching" constrained>
    <LoadingState
      v-if="isSearching"
      label="Searching"
      :detail="query"
      animation="search"
    />
    <div v-else>
      <SearchResults :results="results" />
      <EmptyState
        v-if="!results.length"
        message="No results found"
        icon="search"
      />
    </div>
  </ContentContainer>
</template>
```

### Terminal Tool View Example

```vue
<template>
  <ContentContainer :scrollable="false">
    <div ref="terminalRef" class="terminal-container"></div>
    <EmptyState
      v-if="!hasOutput"
      message="Waiting for output..."
      icon="terminal"
      overlay
    />
  </ContentContainer>
</template>
```

## 🎨 Customization

All components use CSS variables from the design system:

```css
/* Colors */
--text-brand
--text-primary
--text-secondary
--text-tertiary
--background-white-main
--background-gray-main
--border-main

/* Spacing */
--space-2, --space-3, --space-4, etc.

/* Border Radius */
--radius-sm, --radius-md, --radius-lg

/* Typography */
--text-xs, --text-sm, --text-base
--font-normal, --font-medium, --font-semibold
```

## ♿ Accessibility

All components follow accessibility best practices:

- Proper ARIA attributes
- Keyboard navigation support
- Focus indicators
- Screen reader announcements
- Reduced motion support (`prefers-reduced-motion`)

## 🧪 Testing

To test components in isolation, use Storybook:

```bash
npm run storybook
```

## 📝 Contributing

When creating new shared components:

1. Follow the existing component structure
2. Use TypeScript for props and events
3. Include proper documentation
4. Add accessibility features
5. Support dark mode
6. Test with reduced motion preferences
7. Add to this README

## 📚 Related Documentation

- [Tool View Standardization Plan](../../../TOOL_VIEW_STANDARDIZATION_PLAN.md)
- [Design System Guide](../../../docs/DESIGN_SYSTEM.md) (to be created)
- [Component API Reference](../../../docs/COMPONENT_API.md) (to be created)
