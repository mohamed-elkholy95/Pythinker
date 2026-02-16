# Dark Mode Audit - Tool View Components

**Date**: February 15, 2026
**Phase**: 6 - Dark Mode & Theming

---

## 🎯 Audit Objectives

1. **Component Compatibility**: Ensure all shared components work perfectly in dark mode
2. **Animation Visibility**: Verify all loading animations are visible and appealing in dark mode
3. **Color Contrast**: Validate WCAG 2.1 AA contrast ratios in dark mode
4. **CSS Variable Usage**: Ensure components use theme-aware CSS variables
5. **Documentation**: Document dark mode best practices

---

## 🔍 Current Dark Mode System

### Theme Structure
The project uses a **dual-class dark mode system**:
- `:root[data-theme='dark']` - Data attribute approach
- `.dark` - Class-based approach (Tailwind-style)

###CSS Variable Mapping
```css
/* Light Mode */
:root, :root[data-theme='light'] {
  --text-primary: #111827;
  --background-surface: #ffffff;
  --border-main: rgba(15, 23, 42, 0.12);
}

/* Dark Mode */
:root[data-theme='dark'], .dark {
  --text-primary: #e6edf3;
  --background-surface: #161b22;
  --border-main: rgba(48, 54, 61, 0.8);
}
```

---

## 📦 Component Audit Results

### 1. LoadingState.vue
**Status**: ⚠️ **NEEDS REVIEW**

**Current Dark Mode Support**:
- Uses CSS variables: `--text-primary`, `--text-secondary`, `--text-tertiary`
- No explicit `.dark` overrides

**Potential Issues**:
- Loading animations may need contrast adjustments
- Detail text color may be too subtle in dark mode

**Recommended Changes**:
```vue
<style scoped>
/* Add explicit dark mode contrast for detail text */
:global(.dark) .loading-detail {
  color: var(--text-secondary); /* Instead of tertiary */
}
</style>
```

**Testing Checklist**:
- [ ] All 7 animation types visible in dark mode
- [ ] Label text has sufficient contrast
- [ ] Detail text is readable
- [ ] Loading dots are visible

---

### 2. ErrorState.vue
**Status**: ⚠️ **NEEDS ENHANCEMENT**

**Current Dark Mode Support**:
- Uses CSS variables: `--error-red`, `--text-secondary`, `--background-white-main`
- No explicit `.dark` overrides

**Potential Issues**:
- Error icon may be too bright/harsh in dark mode
- Retry button background may not have enough contrast
- Error message may be too subtle

**Recommended Changes**:
```vue
<style scoped>
/* Soften error red in dark mode */
:global(.dark) .error-icon {
  color: #f85149; /* Softer red for dark mode */
  opacity: 0.9;
}

/* Enhance retry button in dark mode */
:global(.dark) .retry-button {
  background: var(--bolt-elements-button-primary-background);
  border-color: var(--border-main);
}

:global(.dark) .retry-button:hover {
  background: var(--bolt-elements-button-primary-backgroundHover);
}

/* Improve error message contrast */
:global(.dark) .error-message {
  color: var(--text-primary); /* Instead of secondary */
}
</style>
```

**Testing Checklist**:
- [ ] Error icon color is appropriate (not too harsh)
- [ ] Error message is easily readable
- [ ] Retry button has sufficient contrast
- [ ] Retry button hover state is visible

---

### 3. EmptyState.vue
**Status**: ✅ **PARTIAL SUPPORT**

**Current Dark Mode Support**:
- Has `.dark` override for overlay background
- Uses CSS variables for text colors

**Existing Dark Mode Code**:
```css
:global(.dark) .empty-state.overlay {
  background: var(--background-mask);
}
```

**Potential Issues**:
- Icon opacity (0.6) may be too subtle in dark mode
- Message text may need enhanced contrast

**Recommended Changes**:
```vue
<style scoped>
/* Increase icon visibility in dark mode */
:global(.dark) .empty-icon {
  opacity: 0.8; /* Up from 0.6 */
  color: var(--text-secondary); /* Ensure proper color */
}

/* Enhance message readability */
:global(.dark) .empty-message {
  color: var(--text-primary); /* Instead of tertiary */
}
</style>
```

**Testing Checklist**:
- [ ] All 6 icon types are visible in dark mode
- [ ] Overlay mode works correctly
- [ ] Message text is readable
- [ ] Action slot buttons have proper dark mode styles

---

### 4. LoadingDots.vue
**Status**: ⚠️ **NEEDS ENHANCEMENT**

**Current Dark Mode Support**:
- Uses CSS variable: `--text-tertiary`
- No explicit `.dark` overrides

**Potential Issues**:
- Dots may be too subtle in dark mode (uses tertiary color)
- Animation may not be visible enough

**Recommended Changes**:
```vue
<style scoped>
/* Enhance dot visibility in dark mode */
:global(.dark) .dot {
  background-color: var(--text-secondary); /* Instead of tertiary */
}
</style>
```

**Testing Checklist**:
- [ ] Dots are clearly visible in dark mode
- [ ] Animation is smooth and noticeable
- [ ] Prefers-reduced-motion still works

---

### 5. ContentContainer.vue
**Status**: ✅ **GOOD SUPPORT**

**Current Dark Mode Support**:
- Has explicit `.dark` scrollbar color overrides
- Uses CSS variables throughout

**Existing Dark Mode Code**:
```css
:global(.dark) .content-container {
  --scrollbar-thumb: var(--fill-tsp-white-main);
  --scrollbar-thumb-hover: var(--fill-tsp-white-dark);
  --scrollbar-thumb-active: var(--border-dark);
}
```

**Status**: ✅ **No changes needed** - scrollbar colors are properly adapted for dark mode

**Testing Checklist**:
- [x] Scrollbar is visible in dark mode
- [ ] Scrollbar hover state works
- [ ] All constraint variants work in dark mode

---

## 🎬 Animation Components Audit

### Animation Components to Review:
1. **GlobeAnimation.vue** - Browser operations
2. **SearchAnimation.vue** - Search operations
3. **FileAnimation.vue** - File operations
4. **TerminalAnimation.vue** - Shell operations
5. **CodeAnimation.vue** - Code execution
6. **SpinnerAnimation.vue** - Generic loading
7. **CheckAnimation.vue** - Success state

### Common Dark Mode Considerations for Animations:

**Color Usage**:
- Light mode: Use `--text-brand` (#3b82f6 - blue)
- Dark mode: May need lighter/brighter variants for visibility

**Opacity**:
- Light mode: 0.6-1.0 range
- Dark mode: 0.7-1.0 range (higher minimum for visibility)

**Gradients**:
- Light mode: Subtle gradients with darker tones
- Dark mode: Brighter gradients with lighter tones

### Recommended Audit Process:

1. **Read each animation component**
2. **Check for hardcoded colors** (should use CSS variables)
3. **Test visibility in dark mode**
4. **Add `.dark` overrides if needed**

---

## 🎨 Dark Mode Enhancement Strategy

### Phase 6.1: Component Enhancements (Priority: HIGH)
**Estimated Time**: 2-3 hours

- [ ] Add dark mode overrides to LoadingState.vue
- [ ] Add dark mode overrides to ErrorState.vue
- [ ] Enhance EmptyState.vue dark mode
- [ ] Add dark mode overrides to LoadingDots.vue
- [ ] Verify ContentContainer.vue (already good)

### Phase 6.2: Animation Audit (Priority: HIGH)
**Estimated Time**: 2-3 hours

- [ ] Audit all 7 animation components
- [ ] Add dark mode color variants where needed
- [ ] Test each animation in both light and dark modes
- [ ] Document any color/opacity adjustments

### Phase 6.3: Visual Testing (Priority: MEDIUM)
**Estimated Time**: 1-2 hours

- [ ] Create dark mode test scenarios
- [ ] Test all states (loading, error, empty, ready)
- [ ] Test all animation types
- [ ] Verify WCAG contrast ratios

### Phase 6.4: Documentation (Priority: MEDIUM)
**Estimated Time**: 1 hour

- [ ] Document dark mode best practices
- [ ] Create dark mode design guidelines
- [ ] Update component documentation with dark mode examples

---

## 📋 Testing Checklist

### Visual Testing Matrix

| Component | Light Mode | Dark Mode | Contrast Check | Notes |
|-----------|------------|-----------|----------------|-------|
| LoadingState (spinner) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (globe) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (search) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (file) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (terminal) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (code) | ⏳ | ⏳ | ⏳ | - |
| LoadingState (check) | ⏳ | ⏳ | ⏳ | - |
| ErrorState | ⏳ | ⏳ | ⏳ | - |
| EmptyState (all icons) | ⏳ | ⏳ | ⏳ | - |
| LoadingDots | ⏳ | ⏳ | ⏳ | - |
| ContentContainer | ⏳ | ⏳ | ⏳ | - |

### Contrast Ratio Requirements (WCAG 2.1 AA)
- **Normal text** (14px+): Minimum 4.5:1
- **Large text** (18px+): Minimum 3:1
- **UI components**: Minimum 3:1

---

## 🛠️ Implementation Guidelines

### Best Practices

1. **Use CSS Variables First**
   ```css
   /* GOOD - adapts automatically */
   .component {
     color: var(--text-primary);
     background: var(--background-surface);
   }

   /* BAD - hardcoded colors */
   .component {
     color: #111827;
     background: #ffffff;
   }
   ```

2. **Add Explicit Overrides When Needed**
   ```css
   /* When CSS variables aren't enough */
   .component {
     opacity: 0.6;
   }

   :global(.dark) .component {
     opacity: 0.8; /* Higher opacity for better visibility */
   }
   ```

3. **Test Both Modes During Development**
   - Toggle dark mode while developing
   - Check contrast with browser DevTools
   - Test on different screen brightness levels

4. **Consider Color Perception**
   - Reds may appear brighter in dark mode → reduce saturation
   - Blues work well in both modes
   - Grays need careful tuning for proper contrast

---

## 📊 Success Metrics

### Phase 6 Completion Criteria

- [ ] **All 5 shared components** have dark mode support
- [ ] **All 7 animations** are visible and appealing in dark mode
- [ ] **100% WCAG AA compliance** for contrast ratios
- [ ] **Zero hardcoded colors** in shared components (all use CSS variables or have dark mode overrides)
- [ ] **Visual testing** completed for all component states
- [ ] **Documentation** updated with dark mode guidelines

---

## 📚 Resources

### Contrast Checkers
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- Chrome DevTools: Lighthouse accessibility audit
- Firefox DevTools: Accessibility inspector

### Dark Mode References
- [Material Design Dark Theme](https://material.io/design/color/dark-theme.html)
- [Apple Human Interface Guidelines - Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode)
- [GitHub Dark Mode Design](https://github.blog/2020-12-08-new-from-universe-2020-dark-mode-github-sponsors-for-companies-and-more/)

---

**Next Steps**: Begin Phase 6.1 - Component Enhancements
