# Vue 3 Coding Standards (Composition API)

This document defines mandatory coding standards for all Vue 3 frontend code in this project.

## Architecture

### Layer Structure (Feature-Sliced Design)

```
frontend/src/
├── pages/            # Route-level components (entry points)
├── features/         # Feature modules (self-contained)
│   └── auth/
│       ├── components/
│       ├── composables/
│       ├── types/
│       └── index.ts  # Barrel file (public API)
├── widgets/          # Composite UI blocks
├── shared/           # Reusable utilities
│   ├── api/          # HTTP client, SSE handlers
│   ├── components/   # Base components (BaseButton, BaseInput)
│   ├── composables/  # Shared stateful logic
│   ├── types/        # Global TypeScript definitions
│   └── utils/        # Pure utility functions
└── app/              # App-level setup (router, store, plugins)
```

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Components | `PascalCase` | `ChatMessage.vue` |
| Base Components | `Base` prefix | `BaseButton.vue` |
| Singleton Components | `The` prefix | `TheSidebar.vue` |
| Composables | `use` prefix | `useSession.ts` |
| Types/Interfaces | `PascalCase` | `SessionState` |
| Files/Folders | `kebab-case` | `chat-message.vue` |

## Global Principles

**Architecture:**
- Always use Vue 3 with Composition API and `<script setup>` syntax by default
- Prefer small, focused components and extract business logic into composables
- Treat AI-related state as a distinct concern: local/composable for volatile data, store for durable cross-screen data

**Safety:**
- Generated code must compile, type-check, and pass ESLint according to project configuration
- Do not modify core build config files (`vite.config`, `tsconfig`, `env`) or aliases unless explicitly instructed
- Do not introduce new dependencies unless explicitly requested and ensure they are added to `package.json`

**Conventions:**
- Respect existing project structure (`components/`, `composables/`, `stores/`, `router/`, `assets/`)
- Respect existing alias configuration (`@/` for `src`)
- Follow naming conventions: `PascalCase` for components, `camelCase` for variables, `useXxx` for composables

## Component Guidelines

### Structure

```vue
<!-- Always use <script setup> with Composition API -->
<script setup lang="ts">
import { ref, computed } from 'vue'

// Props and emits at the top
const props = defineProps<{ title: string }>()
const emit = defineEmits<{ (e: 'update', value: string): void }>()

// Reactive state
const count = ref(0)

// Computed properties
const doubled = computed(() => count.value * 2)
</script>

<template>
  <!-- Template here -->
</template>
```

### Constraints

- Do NOT mix Options API and Composition API in the same component
- Do NOT generate `export default { ... }` Options API unless project clearly uses it everywhere
- Keep components small and focused on a single responsibility (view + light orchestration)
- Extract complex logic (business rules, AI flows, data formatting) into composables
- Avoid monolithic components that contain most business logic; prefer feature modules

### Props and Emits

- Use `defineProps` and `defineEmits` with TypeScript types
- Never mutate props directly; clone into local state if mutation is needed
- Prefer one-way data flow; emit events upward instead of two-way prop mutation
- For custom `v-model`, use `modelValue` and `update:modelValue`

### Props Destructuring (Vue 3.5+)

Vue 3.5+ supports **reactive prop destructuring** natively - destructured variables stay reactive.

```typescript
// ✅ Vue 3.5+ - reactive destructuring with defaults and aliases
<script setup lang="ts">
interface Props {
  msg: string
  count?: number
  foo?: string
}

const {
  msg,
  count = 1,           // default value works
  foo: bar             // aliasing works (props.foo → bar)
} = defineProps<Props>()

watchEffect(() => {
  // Re-runs when props change in Vue 3.5+
  console.log(msg, count, bar)
})
</script>

// ✅ Also valid - traditional access pattern
const props = defineProps<{ title: string }>()
// Use props.title in template and script
```

### Templates

- Keep templates readable; avoid deeply nested inline logic
- Move complex expressions to computed properties or methods
- Always use stable keys (unique IDs) for `v-for`; **NEVER use array index as key**
- Avoid templates exceeding ~150-200 lines; break into child components
- Use `v-if` for conditional rendering when elements are frequently mounted/unmounted
- Use `v-show` only for frequently toggled visibility where keeping elements in DOM is acceptable

```vue
<!-- ❌ BAD - index as key (causes rendering bugs on reorder/delete) -->
<div v-for="(item, index) in items" :key="index">

<!-- ✅ GOOD - unique ID as key (optimal performance and correctness) -->
<div v-for="item in items" :key="item.id">
  {{ item.text }}
</div>

<!-- ✅ GOOD - Object iteration with key binding -->
<ul>
  <li v-for="(value, key, index) in object" :key="key">
    {{ index }}. {{ key }}: {{ value }}
  </li>
</ul>
```

## Reactivity and Performance

### Reactivity Basics

- Use `ref()` for primitives and single values; `reactive()` for plain objects
- Avoid destructuring reactive objects without `toRefs()`; doing so loses reactivity
- Prefer `computed()` for derived values; use `watch()`/`watchEffect()` for side effects only
- Use `shallowRef()` for large objects where you only need shallow reactivity

```typescript
import { ref, reactive, computed, toRefs, onMounted } from 'vue'

// ✅ ref for primitives
const count = ref(0)
const loading = ref(false)

// ✅ reactive for objects
const author = reactive({
  name: 'John Doe',
  books: ['Vue 3 Guide']
})

// ✅ computed for derived values
const publishedBooksMessage = computed(() => {
  return author.books.length > 0 ? 'Yes' : 'No'
})

// ❌ BAD - loses reactivity
const { name, books } = reactive({ name: 'John', books: [] })

// ✅ GOOD - preserves reactivity with toRefs
const state = reactive({ name: 'John', books: [] })
const { name, books } = toRefs(state)

// ✅ Lifecycle hooks
onMounted(() => {
  console.log(`Initial count: ${count.value}`)
})
```

### Performance

- Avoid expensive computations directly in templates; move them into computed properties
- Avoid massive deeply nested reactive objects when normalized structures suffice
- Use `v-memo`, `v-once`, and lazy components only when profiling shows a benefit
- Prefer stable keys with IDs and avoid re-creating heavy objects/functions inline each render

### AI Data Specific

- Treat large AI histories and responses as server state; avoid duplicating entire backend truth in global stores
- Use `shallowRef()` for large chat logs/tool traces - only `.value` replacement triggers reactivity, not deep mutations
- Trim/paginate long histories instead of keeping multi-day conversations for every tab in memory
- Avoid watchers on huge blobs (entire conversation objects); watch small slices or IDs instead

```typescript
import { shallowRef } from 'vue'

// ✅ GOOD - shallowRef for large AI data
const chatHistory = shallowRef<Message[]>([])

// Deep mutation does NOT trigger reactivity (intentional for performance)
chatHistory.value.push(newMessage) // Won't trigger re-render

// Replace .value to trigger reactivity
chatHistory.value = [...chatHistory.value, newMessage] // Triggers re-render
```

## State Management

### Decision Tree

| Scope | Solution |
|-------|----------|
| Purely local UI (inputs, open panels, loading flags) | Component-local state (`ref`, `reactive`) |
| Reusable logic shared by subset of components | Composables (`useXxx()`) |
| Global cross-route state (auth, settings, layout) | Pinia stores (`useXxxStore()`) |

### Pinia Patterns

- Create small, domain-focused stores rather than a single global one
- Place all mutations inside actions; do not mutate store state directly from components
- Use getters only for derived state, not for storing precomputed values
- Do NOT put every piece of state in Pinia; if state is local, keep it local
- **CRITICAL**: Use `storeToRefs()` when destructuring state/getters to preserve reactivity

```typescript
// stores/useAiSettingsStore.ts
import { defineStore } from 'pinia'

export const useAiSettingsStore = defineStore('aiSettings', {
  state: () => ({
    model: 'gpt-4',
    temperature: 0.7,
  }),
  getters: {
    isHighTemperature: (state) => state.temperature > 0.8,
  },
  actions: {
    setModel(model: string) {
      this.model = model
    },
  },
})
```

### Destructuring from Stores (storeToRefs)

```vue
<script setup>
import { storeToRefs } from 'pinia'
import { useAiSettingsStore } from '@/stores/aiSettings'

const store = useAiSettingsStore()

// ✅ GOOD - storeToRefs for state and getters (preserves reactivity)
const { model, temperature, isHighTemperature } = storeToRefs(store)

// ✅ GOOD - Actions can be destructured directly (bound to store)
const { setModel } = store

// ❌ BAD - Direct destructure loses reactivity
// const { model } = store // Don't do this!
</script>
```

### AI-Specific State

| State Type | Where to Store |
|------------|----------------|
| Request lifecycle (loading, streaming, abort signals) | Composables (`useAiChat`) |
| Durable settings (model, temperature, usage counters) | Pinia stores (`useAiSettingsStore`) |
| Chat histories and responses | Server state via data-fetching layer |
| Streaming/SSE/WebSocket logic | Request-scoped composables |

## Async and API Guidelines

### Network Calls

- Encapsulate network requests in composables or store actions, not scattered across components
- Always handle loading and error states explicitly; never assume success
- Use `async/await` consistently; avoid mixing `.then/.catch` with `async/await`
- For AI APIs, rely on backend endpoints; do not expose provider API keys in frontend code

### Agent Constraints

- Do NOT invent global components, plugins, or configuration that do not exist in the project
- Do NOT casually modify core shared composables or stores in ways that may break existing behavior
- Prefer iterative, small changes (add a prop, add a method, adjust one flow) over generating large, monolithic components

## TypeScript Requirements

- Define explicit interfaces/types for props, emits, and store state
- Avoid using `any` unless absolutely necessary; prefer precise types
- Keep code TS-friendly even in edge cases

```typescript
// ❌ BAD - any type
const data: any = await fetchData()

// ✅ GOOD - explicit types
interface ChatResponse {
  id: string
  content: string
  timestamp: Date
}
const data: ChatResponse = await fetchData()
```

## Routing and Navigation

- Use Vue Router 4 patterns: `createRouter` and `createWebHistory`
- Define routes in a central routes file or feature modules
- Lazy-load large route components via dynamic imports

```typescript
// routes/index.ts
const routes = [
  {
    path: '/chat/:id',
    component: () => import('@/pages/ChatPage.vue'), // Lazy load
  },
]
```

## Implementation Patterns

### Composables for Stateful Logic

```typescript
// composables/useSession.ts
import { ref, computed } from 'vue'
import type { Session } from '@/types/session'

export function useSession() {
  const session = ref<Session | null>(null)
  const isActive = computed(() => session.value?.status === 'active')

  async function loadSession(id: string): Promise<void> {
    // Load session logic
  }

  return { session, isActive, loadSession }
}
```

### Type-Safe API Layer

```typescript
// api/session.ts
import type { Session, CreateSessionDTO } from '@/types/session'
import { apiClient } from './client'

export const sessionApi = {
  create: (dto: CreateSessionDTO): Promise<Session> =>
    apiClient.put('/sessions', dto),

  getById: (id: string): Promise<Session> =>
    apiClient.get(`/sessions/${id}`),
}
```

### Barrel Files for Encapsulation

```typescript
// features/auth/index.ts
export { LoginForm } from './components/LoginForm.vue'
export { useAuth } from './composables/useAuth'
export type { AuthState } from './types'
// Internal implementation details NOT exported
```

## Documentation

- For new complex components, composables, or stores, include concise JSDoc/TSDoc comments for public APIs
- Add brief comments only for non-obvious logic, not for trivial lines
- Keep documentation near the code

## AI Code Generation Workflow

**When generating Vue code:**
1. Generate small, focused changes: first create component skeleton, then add props/emits, then logic, then styling
2. Create or update composables first for complex logic, then wire them into components
3. When adding shared state, create or update a Pinia store before building the UI

**Validation loop (always run after changes):**
```bash
cd frontend && bun run lint && bun run type-check
```
