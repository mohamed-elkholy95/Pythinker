# Tool View Components Standardization Plan

## 📋 Executive Summary

This document outlines the standardization plan for all tool view components in Pythinker to ensure consistent design, user experience, and maintainability across the agent interface.

## 🎯 Goals

1. **Visual Consistency**: Unified design language across all tool views
2. **Component Reusability**: Shared base components and utilities
3. **Animation Standards**: Consistent loading/activity states
4. **Accessibility**: Keyboard navigation and screen reader support
5. **Performance**: Optimized rendering and state management
6. **Maintainability**: Clear component structure and documentation

---

## 🎨 Design System

### Color Palette (CSS Variables)
```css
/* Primary Colors */
--text-brand: #3b82f6              /* Brand blue */
--text-primary: rgba(0,0,0,0.9)    /* Main text */
--text-secondary: rgba(0,0,0,0.7)  /* Secondary text */
--text-tertiary: rgba(0,0,0,0.5)   /* Tertiary text */

/* Backgrounds */
--background-white-main: #ffffff
--background-gray-main: #f5f5f7
--fill-tsp-gray-main: #f0f0f2
--fill-white: #ffffff

/* Borders */
--border-main: rgba(0,0,0,0.1)
--border-light: rgba(0,0,0,0.08)
--border-dark: rgba(0,0,0,0.15)

/* State Colors */
--success-green: #10b981
--warning-yellow: #f59e0b
--error-red: #ef4444
--info-blue: #3b82f6

/* Dark Mode Variants */
dark:--text-primary: rgba(255,255,255,0.95)
dark:--text-secondary: rgba(255,255,255,0.7)
dark:--text-tertiary: rgba(255,255,255,0.5)
```

### Typography Scale
```css
/* Font Families */
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
--font-mono: Menlo, Monaco, "Courier New", monospace

/* Font Sizes */
--text-xs: 12px      /* Labels, meta info */
--text-sm: 13px      /* Body text */
--text-base: 14px    /* Default text */
--text-lg: 16px      /* Headings */
--text-xl: 18px      /* Large headings */

/* Font Weights */
--font-normal: 400
--font-medium: 500
--font-semibold: 600
```

### Spacing System
```css
/* Base unit: 4px */
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-5: 20px
--space-6: 24px
--space-8: 32px
--space-12: 48px
--space-16: 64px
```

### Border Radius
```css
--radius-sm: 6px
--radius-md: 8px
--radius-lg: 12px
--radius-xl: 16px
--radius-2xl: 22px
--radius-full: 9999px
```

---

## 🏗️ Component Architecture

### Base Component Structure

All tool view components should follow this structure:

```vue
<template>
  <div class="tool-view-container">
    <!-- Loading State -->
    <LoadingState v-if="isLoading" :label="loadingLabel" :detail="loadingDetail" />

    <!-- Empty State -->
    <EmptyState v-else-if="isEmpty" :message="emptyMessage" />

    <!-- Error State -->
    <ErrorState v-else-if="hasError" :error="errorMessage" />

    <!-- Content -->
    <div v-else class="tool-view-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import EmptyState from '@/components/toolViews/shared/EmptyState.vue';
import ErrorState from '@/components/toolViews/shared/ErrorState.vue';

// Component logic
</script>

<style scoped>
.tool-view-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.tool-view-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
```

---

## 📦 Shared Components

### 1. LoadingState.vue
**Purpose**: Standardized loading animations for all tool views

```vue
<template>
  <div class="loading-state">
    <div class="loading-animation">
      <component :is="animationComponent" />
    </div>
    <div class="loading-text">
      <span class="loading-label">{{ label }}</span>
      <LoadingDots />
    </div>
    <div v-if="detail" class="loading-detail">{{ detail }}</div>
  </div>
</template>
```

**Animation Variants**:
- `SpinnerAnimation` - Generic loading
- `GlobeAnimation` - Browser/network operations
- `SearchAnimation` - Search operations
- `FileAnimation` - File operations
- `TerminalAnimation` - Command execution

### 2. EmptyState.vue
**Purpose**: Consistent empty states

```vue
<template>
  <div class="empty-state">
    <component :is="iconComponent" class="empty-icon" />
    <p class="empty-message">{{ message }}</p>
    <slot name="action"></slot>
  </div>
</template>
```

### 3. ErrorState.vue
**Purpose**: Unified error display

```vue
<template>
  <div class="error-state">
    <AlertCircle class="error-icon" />
    <p class="error-message">{{ error }}</p>
    <button v-if="retryable" @click="$emit('retry')" class="retry-button">
      Try Again
    </button>
  </div>
</template>
```

### 4. LoadingDots.vue
**Purpose**: Animated dots for loading states

```vue
<template>
  <span class="loading-dots">
    <span v-for="i in 3" :key="i" class="dot" :style="{ animationDelay: `${(i-1) * 200}ms` }"></span>
  </span>
</template>
```

### 5. ContentContainer.vue
**Purpose**: Standard content wrapper with consistent padding and scrolling

```vue
<template>
  <div class="content-container" :class="{ centered, scrollable }">
    <div class="content-inner" :class="{ constrained }">
      <slot></slot>
    </div>
  </div>
</template>
```

---

## 🎬 Animation Standards

### Loading Animations
All loading animations should:
- Duration: 1.5s - 3s per cycle
- Easing: `cubic-bezier(0.4, 0, 0.2, 1)` or `ease-in-out`
- Colors: Use `--text-brand` or gradient with opacity
- Performance: Use `transform` and `opacity` only (GPU accelerated)

### Standard Keyframes

```css
/* Pulse (for activity indicators) */
@keyframes pulse {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.05); }
}

/* Spin (for loading spinners) */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Bounce (for dots) */
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

/* Fade In */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Slide Up */
@keyframes slideUp {
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
```

### Transition Standards

```css
/* Default transition */
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

/* Fast interaction */
transition: opacity 0.15s ease-in-out;

/* Smooth expansion */
transition: height 0.3s cubic-bezier(0.4, 0, 0.2, 1);

/* Color changes */
transition: color 0.2s ease, background-color 0.2s ease;
```

---

## 📱 Responsive Design

### Breakpoints
```css
/* Mobile */
@media (max-width: 640px) { }

/* Tablet */
@media (min-width: 641px) and (max-width: 1024px) { }

/* Desktop */
@media (min-width: 1025px) { }
```

### Content Constraints
```css
/* Narrow content (optimal reading width) */
.content-narrow {
  max-width: 640px;
  margin: 0 auto;
}

/* Medium content */
.content-medium {
  max-width: 960px;
  margin: 0 auto;
}

/* Full width */
.content-full {
  width: 100%;
}
```

---

## ♿ Accessibility Guidelines

### Required Attributes
1. **ARIA Labels**: All interactive elements must have descriptive labels
2. **Keyboard Navigation**: Tab order must be logical
3. **Focus Indicators**: Visible focus states for all controls
4. **Screen Reader**: Announce loading/error states

### Examples

```vue
<!-- Loading state announcement -->
<div role="status" aria-live="polite" aria-busy="true">
  <span class="sr-only">Loading {{ label }}...</span>
  <LoadingAnimation />
</div>

<!-- Error announcement -->
<div role="alert" aria-live="assertive">
  <span class="sr-only">Error: {{ errorMessage }}</span>
  <ErrorDisplay :error="errorMessage" />
</div>

<!-- Interactive content -->
<button
  aria-label="Retry operation"
  @click="handleRetry"
  :disabled="isLoading"
>
  Retry
</button>
```

---

## 🔧 Refactoring Plan

### Phase 1: Shared Components (Week 1)
**Priority: HIGH**

- [x] Create `shared/LoadingState.vue` with all animation variants
- [x] Create `shared/EmptyState.vue`
- [x] Create `shared/ErrorState.vue`
- [x] Create `shared/LoadingDots.vue`
- [x] Create `shared/ContentContainer.vue`
- [x] Create `shared/animations/` directory with all animation components
- [x] Document prop interfaces and usage examples

### Phase 2: Animation Library (Week 1)
**Priority: HIGH**

- [x] Create `animations/GlobeAnimation.vue` (browser operations)
- [x] Create `animations/SearchAnimation.vue` (search operations)
- [x] Create `animations/FileAnimation.vue` (file operations)
- [x] Create `animations/TerminalAnimation.vue` (shell operations)
- [x] Create `animations/CodeAnimation.vue` (code execution)
- [x] Create `animations/SpinnerAnimation.vue` (generic loading)

### Phase 3: Refactor Existing Components (Week 2)
**Priority: MEDIUM**

Tool views to refactor:
- [x] `VNCContentView.vue` - Extract animation to shared component
- [x] `TerminalContentView.vue` - Standardize empty state
- [x] `EditorContentView.vue` - Add loading/error states
- [x] `SearchContentView.vue` - Use shared animation component
- [x] `GenericContentView.vue` - Improve layout consistency
- [x] `BrowserToolView.vue` (legacy) - Migrate to unified system
- [x] `ShellToolView.vue` (legacy) - Migrate to unified system
- [ ] `FileToolView.vue` (legacy) - Migrate to unified system
- [ ] `McpToolView.vue` (legacy) - Migrate to unified system
- [ ] `SearchToolView.vue` (legacy) - Migrate to unified system

### Phase 4: Composables & Utilities (Week 2)
**Priority: MEDIUM**

- [ ] Create `useLoadingState.ts` - Loading state management
- [ ] Create `useErrorHandler.ts` - Error handling utilities
- [ ] Create `useContentState.ts` - Content state management
- [ ] Create `useAnimation.ts` - Animation control utilities
- [ ] Update `useContentConfig.ts` - Add state management

### Phase 5: Documentation & Testing (Week 3)
**Priority: MEDIUM**

- [ ] Write Storybook stories for all shared components
- [ ] Create visual regression tests
- [ ] Document design tokens in style guide
- [ ] Create component usage guidelines
- [ ] Add accessibility audit
- [ ] Performance benchmarks

### Phase 6: Dark Mode & Theming (Week 3)
**Priority: LOW**

- [ ] Audit all components for dark mode support
- [ ] Create theme switching utility
- [ ] Test all animations in dark mode
- [ ] Document theme customization

---

## 📝 Component Specifications

### VNCContentView (Standardized)

```vue
<template>
  <ContentContainer :scrollable="false" padding="none" class="vnc-view">
    <!-- Loading State with Globe Animation -->
    <LoadingState
      v-if="showPlaceholder"
      :label="placeholderLabel || 'Loading'"
      :detail="placeholderDetail"
      :is-active="isActive"
      animation="globe"
    />

    <!-- Live VNC Viewer -->
    <VNCViewer
      v-else-if="enabled"
      :session-id="sessionId"
      :enabled="enabled"
      :view-only="viewOnly"
      @connected="emit('connected')"
      @disconnected="emit('disconnected')"
      class="vnc-viewer"
    />

    <!-- Static Screenshot Fallback -->
    <img
      v-else-if="screenshot"
      :src="screenshot"
      alt="Screenshot"
      class="vnc-screenshot"
    />

    <!-- Take Over Button Slot -->
    <slot name="takeover"></slot>
  </ContentContainer>
</template>
```

### TerminalContentView (Standardized)

```vue
<template>
  <ContentContainer :scrollable="false" padding="none" class="terminal-view">
    <div class="terminal-shell">
      <!-- xterm.js Terminal -->
      <div ref="terminalRef" class="terminal-surface"></div>

      <!-- Empty State Overlay -->
      <EmptyState
        v-if="!content"
        :message="emptyLabel"
        :icon="emptyIcon"
        overlay
      />
    </div>
  </ContentContainer>
</template>
```

### SearchContentView (Standardized)

```vue
<template>
  <ContentContainer :centered="isSearching" :constrained="!isSearching">
    <!-- Loading State with Search Animation -->
    <LoadingState
      v-if="isSearching"
      :label="t('Searching')"
      :detail="query ? `\"${query}\"` : ''"
      animation="search"
    />

    <!-- Search Results -->
    <div v-else class="search-results">
      <div
        v-for="(result, index) in results"
        :key="result.link || index"
        class="search-result"
      >
        <a :href="result.link" target="_blank" class="search-title">
          {{ result.title }}
        </a>
        <div class="search-snippet">{{ result.snippet }}</div>
      </div>
      <EmptyState
        v-if="!results?.length"
        message="No results found"
        icon="search"
      />
    </div>
  </ContentContainer>
</template>
```

### EditorContentView (Standardized)

```vue
<template>
  <ContentContainer :scrollable="false" padding="none" class="editor-view">
    <LoadingState
      v-if="isLoading"
      :label="filename ? 'Loading file' : 'Loading content'"
      :detail="filename"
      animation="file"
    />
    <ErrorState v-else-if="error" :error="error" />
    <section v-else class="editor-body">
      <!-- Monaco Editor -->
      <MonacoEditor
        :value="content"
        :filename="filename"
        :read-only="true"
        theme="vs"
      />
    </section>
  </ContentContainer>
</template>
```

---

## 🎨 Style Guide

### Layout Patterns

```vue
<!-- Full height container -->
<div class="tool-view-container">
  <div class="tool-view-header"><!-- Header --></div>
  <div class="tool-view-content"><!-- Scrollable content --></div>
  <div class="tool-view-footer"><!-- Footer --></div>
</div>

<style scoped>
.tool-view-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

.tool-view-content {
  flex: 1;
  min-height: 0; /* Important for flex overflow */
  overflow: auto;
}
</style>
```

### Card Pattern

```vue
<div class="card">
  <div class="card-header">
    <h3 class="card-title">Title</h3>
  </div>
  <div class="card-body">Content</div>
</div>

<style scoped>
.card {
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.card-header {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-light);
}

.card-body {
  padding: var(--space-4);
}
</style>
```

---

## 🧪 Testing Strategy

### Unit Tests
```typescript
// Example: LoadingState.test.ts
describe('LoadingState', () => {
  it('renders label and detail', () => {
    const wrapper = mount(LoadingState, {
      props: { label: 'Loading', detail: 'Please wait...' }
    });
    expect(wrapper.text()).toContain('Loading');
    expect(wrapper.text()).toContain('Please wait...');
  });

  it('shows correct animation based on type', () => {
    const wrapper = mount(LoadingState, {
      props: { animation: 'globe' }
    });
    expect(wrapper.findComponent(GlobeAnimation).exists()).toBe(true);
  });
});
```

### Visual Regression Tests
```typescript
// Example: Chromatic/Storybook
export const Default = () => ({
  components: { LoadingState },
  template: '<LoadingState label="Loading" animation="globe" />'
});

export const WithDetail = () => ({
  components: { LoadingState },
  template: '<LoadingState label="Searching" detail="example.com" animation="search" />'
});
```

---

## 📊 Success Metrics

### Code Quality
- [ ] **Component Reusability**: 80%+ code reuse across tool views
- [ ] **Bundle Size**: Reduce component bundle by 25%
- [ ] **Type Safety**: 100% TypeScript coverage

### User Experience
- [ ] **Consistency**: 100% of tool views use standardized states
- [ ] **Performance**: All animations run at 60fps
- [ ] **Accessibility**: WCAG 2.1 AA compliance

### Developer Experience
- [ ] **Development Time**: 50% reduction in time to create new tool views
- [ ] **Documentation**: 100% of components documented with examples
- [ ] **Maintenance**: 40% reduction in bug reports related to UI consistency

---

## 🚀 Implementation Checklist

### Immediate Actions (This Week)
- [x] Create this standardization plan
- [ ] Review plan with team
- [ ] Set up shared components directory structure
- [ ] Create base LoadingState component
- [ ] Create animation component library

### Short Term (Next 2 Weeks)
- [ ] Refactor all content view components
- [ ] Create comprehensive Storybook stories
- [ ] Update existing tool views to use shared components
- [ ] Write migration guide for developers

### Medium Term (Next Month)
- [ ] Complete accessibility audit
- [ ] Implement dark mode support
- [ ] Performance optimization
- [ ] Create design system documentation site

### Long Term (Next Quarter)
- [ ] Theme customization system
- [ ] Advanced animation library
- [ ] Component marketplace/library
- [ ] Automated visual regression testing

---

## 📚 Additional Resources

### Related Documentation
- [Component API Reference](./docs/COMPONENT_API.md) (to be created)
- [Animation Guidelines](./docs/ANIMATIONS.md) (to be created)
- [Accessibility Checklist](./docs/ACCESSIBILITY.md) (to be created)
- [Performance Guide](./docs/PERFORMANCE.md) (to be created)

### Design References
- Figma Design System (link when available)
- Storybook Component Library (link when available)
- Living Style Guide (link when available)

---

## 🤝 Contributing

When creating or modifying tool view components:

1. **Follow the Base Structure**: Use the standardized component template
2. **Reuse Shared Components**: Don't recreate loading/empty/error states
3. **Use Design Tokens**: Reference CSS variables, not hardcoded values
4. **Test Accessibility**: Ensure keyboard navigation and screen reader support
5. **Document Changes**: Update this plan and component documentation
6. **Create Stories**: Add Storybook stories for all new components

---

## ✅ Review & Approval

| Role | Name | Status | Date |
|------|------|--------|------|
| Frontend Lead | - | Pending | - |
| UX Designer | - | Pending | - |
| Accessibility | - | Pending | - |
| Engineering | - | Pending | - |

---

**Last Updated**: January 26, 2026
**Version**: 1.0.0
**Status**: Draft - Awaiting Review
