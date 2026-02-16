# Frontend/Vue 3 Skill Auto-Activation Hook

## Overview

A PreToolUse hook that automatically detects frontend/Vue 3 code operations and recommends the appropriate Vue or frontend design skill. This ensures Claude Code consistently uses expert-level Vue 3 and frontend design capabilities when working on Pythinker's frontend codebase.

## How It Works

### 1. Hook Triggers
The hook (`~/.claude/hooks/frontend_skill_activator.py`) monitors these operations:
- **Edit**: File content modifications
- **Write**: New file creation
- **MultiEdit**: Multiple file edits
- **Bash**: Command execution (detects npm, bun, vite, vitest commands)
- **Read**: File reading (for context)

### 2. Context Detection

#### Directory-Based Detection
Monitors Pythinker frontend structure:
- `/frontend/src/components/*.vue` - Vue components
- `/frontend/src/pages/*.vue` - Page components
- `/frontend/src/composables/*.ts` - Composables (40+ in Pythinker)
- `/frontend/src/api/*.ts` - API client (SSE, HTTP, WebSocket)
- `/frontend/src/types/*.ts` - TypeScript types
- `/frontend/src/stores/*.ts` - Pinia stores
- `/frontend/src/router/*.ts` - Vue Router config
- `/frontend/tests/**/*.test.ts` - Vitest tests
- `/frontend/src/utils/*.ts` - Utility functions
- `/frontend/src/main.ts` - Entry point

#### Content-Based Detection (11 Priority Levels)

**Priority 1: Vue Composition API**
- Keywords: `<script setup>`, `defineProps`, `defineEmits`, `ref()`, `reactive()`, `computed()`, `watch()`, `onMounted`, etc.
- Skill: `vue-best-practices:vue-best-practices`

**Priority 2: Vue Router**
- Keywords: `createRouter`, `useRouter`, `useRoute`, `RouterView`, `beforeEach`, `NavigationGuard`
- Skill: `vue-best-practices:vue-router-best-practices`

**Priority 3: Pinia**
- Keywords: `defineStore`, `storeToRefs`, `usePinia`, `$state`, `$patch`, `getters:`, `actions:`
- Skill: `vue-best-practices:vue-pinia-best-practices`

**Priority 4: Testing**
- Keywords: `mount()`, `@vue/test-utils`, `vitest`, `describe`, `it`, `expect`, `toBe`, `vi.mock`
- Skill: `vue-best-practices:vue-testing-best-practices`

**Priority 5: Composables**
- Keywords: `export function use`, `toRefs()`, `readonly()`, `shallowRef()`, `MaybeRef`, `toValue()`
- Skill: `vue-best-practices:vue-best-practices` or `vue-best-practices:create-adaptable-composable`

**Priority 6: API Client**
- Keywords: `EventSource`, `fetch()`, `WebSocket`, `async/await`, `Promise`, `text/event-stream`
- Skill: `vue-best-practices:vue-best-practices`
- Examples: Pythinker's SSE streaming, agent API, auth API

**Priority 7: TypeScript Types**
- Keywords: `export interface`, `export type`, `PropType`, `Ref<`, `ComputedRef<`
- Skill: `vue-best-practices:vue-best-practices`

**Priority 8: Visual Design**
- Keywords: `<style>`, `tailwind`, `@apply`, `class=`, `bg-`, `flex`, `transition`, `hover:`
- Skill: `frontend-design:frontend-design` (for new components or heavy styling)

**Priority 9: Debugging**
- Keywords: `console.log`, `debugger`, `Error:`, `TODO`, `FIXME`
- Skill: `vue-best-practices:vue-debug-guides`

**Priority 10: Options API (Legacy)**
- Keywords: `export default {`, `data()`, `methods:`, `computed:`, `this.$`
- Skill: `vue-best-practices:vue-options-api-best-practices`

**Priority 11: JSX/TSX**
- Keywords: `import { h }`, `render()`, `className=`, `onClick={`, `.jsx`, `.tsx`
- Skill: `vue-best-practices:vue-jsx-best-practices`

### 3. Skill Recommendations

#### Vue Best Practices Skills

| Skill | Description | Use Cases |
|-------|-------------|-----------|
| `vue-best-practices:vue-best-practices` | Main Vue 3 skill | Components, composables, API client, types, general Vue work |
| `vue-best-practices:vue-router-best-practices` | Vue Router 4 expert | Router config, navigation guards, route params |
| `vue-best-practices:vue-pinia-best-practices` | State management | Stores, state, getters, actions |
| `vue-best-practices:vue-testing-best-practices` | Testing expert | Vitest, Vue Test Utils, component tests, E2E |
| `vue-best-practices:create-adaptable-composable` | Advanced composables | MaybeRef, MaybeRefOrGetter, reactive inputs |
| `vue-best-practices:vue-debug-guides` | Debugging | Runtime errors, warnings, hydration issues |
| `vue-best-practices:vue-jsx-best-practices` | JSX in Vue | Render functions, JSX syntax |
| `vue-best-practices:vue-options-api-best-practices` | Options API (legacy) | data(), methods, this context |

#### Frontend Design Skill

| Skill | Description | Use Cases |
|-------|-------------|-----------|
| `frontend-design:frontend-design` | Production UI design | New components, visual design, distinctive aesthetics, styling |

### 4. Recommendation Display

```
╔════════════════════════════════════════════════════════════════╗
║  ⚡ VUE SKILL ACTIVATION RECOMMENDED                    ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Context: Vue component development                            ║
║  File: ChatMessage.vue                                          ║
║                                                                ║
║  Recommended: vue-best-practices:vue-best-practices            ║
║  Vue 3 Expert • Composition API • <script setup> • TypeScript • Reactivity║
║                                                                ║
║  Uses Composition API with <script setup> and TypeScript        ║
║                                                                ║
║  To use: Skill tool will invoke automatically on next action   ║
║  To disable hook: export ENABLE_FRONTEND_SKILL_HOOK=0          ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

## Usage

### For Claude Code (AI Agent)

**CRITICAL**: When you see a hook recommendation message, **immediately invoke the recommended skill** using the Skill tool:

```
# Invoke skill with no arguments
Skill tool: vue-best-practices:vue-best-practices

# Or invoke skill with specific task
Skill tool: vue-best-practices:vue-best-practices
Arguments: "Implement composable with proper reactivity patterns"
```

**Do NOT**:
- ❌ Ignore the recommendation
- ❌ Proceed without invoking the skill
- ❌ Use generic capabilities instead of specialized skills

**DO**:
- ✅ Immediately invoke the recommended skill
- ✅ Let the specialized skill handle the work
- ✅ Trust the skill's comprehensive Vue 3 expertise

### For Users

The hook runs automatically - no action needed. Messages appear in Claude Code's conversation.

**To disable temporarily:**
```bash
export ENABLE_FRONTEND_SKILL_HOOK=0
```

**To re-enable:**
```bash
unset ENABLE_FRONTEND_SKILL_HOOK
```

## Pythinker Frontend Coverage

### Components (50+ Vue components)
- `ChatMessage.vue`, `ChatBox.vue`, `SandboxViewer.vue`
- `LiveMiniPreview.vue`, `SessionFileList.vue`
- `LeftPanel.vue`, `PhaseGroup.vue`, `SkillPicker.vue`
- All detected and trigger `vue-best-practices:vue-best-practices`

### Composables (40+ custom composables)
- `useSSEConnection.ts`, `useAuth.ts`, `useSandboxInput.ts`
- `useSessionStreamController.ts`, `useCircuitBreaker.ts`
- `usePlotlyChart.ts`, `useSkills.ts`, `useTimeline.ts`
- All detected and trigger appropriate Vue skills

### API Client
- `client.ts` - Main HTTP client
- `agent.ts` - Agent API (SSE streaming)
- `auth.ts` - Authentication
- `skills.ts` - Skills API
- All detected and trigger `vue-best-practices:vue-best-practices`

### TypeScript Types
- `message.ts`, `event.ts`, `response.ts`, `panel.ts`, `canvas.ts`
- All detected and trigger `vue-best-practices:vue-best-practices`

### Tests
- Vitest tests in `__tests__` directories
- All detected and trigger `vue-best-practices:vue-testing-best-practices`

## Installation

The hook is already installed at:
- Script: `~/.claude/hooks/frontend_skill_activator.py`
- Config: `~/.claude/hooks/hooks.json` (registered alongside Python hook)

To reinstall or update:

```bash
# Ensure script is executable
chmod +x ~/.claude/hooks/frontend_skill_activator.py

# Verify hooks.json includes frontend hook
cat ~/.claude/hooks/hooks.json | python3 -m json.tool
```

## Configuration

### Hooks.json Entry
```json
{
  "hooks": [
    {
      "type": "command",
      "command": "python3 /Users/panda/.claude/hooks/frontend_skill_activator.py"
    }
  ],
  "matcher": "Edit|Write|MultiEdit|Bash|Read",
  "description": "Activate Vue 3 and frontend design skills when working on frontend code"
}
```

### Customization

Edit `frontend_skill_activator.py` to adjust detection patterns.

## Decision Matrix

| File Path | Content | Recommended | Type |
|-----------|---------|-------------|------|
| `frontend/src/components/*.vue` | Any | vue-best-practices | skill |
| `frontend/src/pages/*.vue` | Any | vue-best-practices | skill |
| `frontend/src/composables/*.ts` | `ref()`, `computed()` | vue-best-practices | skill |
| `frontend/src/composables/*.ts` | `MaybeRef`, `toValue()` | create-adaptable-composable | skill |
| `frontend/src/router/*.ts` | `createRouter` | vue-router-best-practices | skill |
| `frontend/src/stores/*.ts` | `defineStore` | vue-pinia-best-practices | skill |
| `frontend/src/api/*.ts` | `fetch()`, `EventSource` | vue-best-practices | skill |
| `frontend/tests/*.test.ts` | `mount()`, `vitest` | vue-testing-best-practices | skill |
| `frontend/src/*.vue` | `<style>`, `tailwind` (new) | frontend-design | design |
| `frontend/src/*.vue` | `data()`, `methods:` | vue-options-api-best-practices | skill |

## Benefits

1. **Comprehensive Coverage**: Detects all Vue 3 patterns in Pythinker frontend
2. **Context-Aware**: 11 priority levels for accurate skill selection
3. **Professional Quality**: Ensures Vue best practices (Composition API, TypeScript)
4. **Automatic Detection**: No manual skill invocation needed
5. **Non-Blocking**: Shows recommendation but allows work to continue
6. **Session-Scoped**: Avoids repetitive recommendations
7. **Design-Aware**: Suggests frontend-design skill for visual work

## Troubleshooting

### Hook Not Triggering
```bash
# Check hook is installed
ls -la ~/.claude/hooks/frontend_skill_activator.py

# Verify executable permission
chmod +x ~/.claude/hooks/frontend_skill_activator.py
```

### Check Debug Logs
```bash
tail -20 /tmp/frontend-skill-hook-log.txt
```

### Verify hooks.json
```bash
cat ~/.claude/hooks/hooks.json | python3 -m json.tool
```

### Hook Disabled
```bash
# Check environment variable
echo $ENABLE_FRONTEND_SKILL_HOOK

# Re-enable if disabled
unset ENABLE_FRONTEND_SKILL_HOOK
```

## Related Documentation

- **CLAUDE.md**: Project guidelines and automatic activation workflow
- **MEMORY.md**: Critical action required when hook messages appear
- **PYTHON_SKILL_AUTO_ACTIVATION.md**: Python skill hook documentation
- **Vue Standards**: `docs/guides/VUE_STANDARDS.md`

## Change Log

### 2026-02-16 - Initial Release
- Created PreToolUse hook for frontend/Vue 3 skill auto-activation
- 11 priority levels for content-based detection
- Comprehensive coverage of Pythinker frontend (components, composables, API, types, tests)
- Support for Vue Router, Pinia, Vitest, frontend design
- Session-scoped recommendations
- Updated CLAUDE.md and MEMORY.md with workflow documentation
