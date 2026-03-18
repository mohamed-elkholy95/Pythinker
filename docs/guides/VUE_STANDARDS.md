# Vue 3 Frontend Standards

This document describes how the frontend works today and what new changes should aim for.

## Current Repo Reality

The frontend currently uses:

- Vue 3 with Composition API
- TypeScript with `strict: true`
- Vite
- Pinia
- Vue Router

The current directory shape is based on the existing repo, not feature-sliced architecture:

```text
frontend/src/
├── api/
├── assets/
├── components/
├── composables/
├── config/
├── constants/
├── contracts/
├── lib/
├── locales/
├── pages/
├── plugins/
├── router/
├── stores/
├── types/
└── utils/
```

Do not introduce `features/`, `widgets/`, `shared/`, or `app/` directories unless the task explicitly includes a broader frontend architecture migration.

## Enforced by Tooling

- `bun run type-check` must pass.
- `bun run lint:check` must pass.
- Use the `@/` alias for `src`.
- TypeScript `strict` mode is enabled.

### Important TypeScript Note

`strict: true` does not mean the repo is fully `any`-free.

- `@typescript-eslint/no-explicit-any` is currently disabled in `frontend/eslint.config.js`.
- Existing `any` usages remain in the codebase.
- Do not add new `any` unless a better type would be disproportionate to the task. Prefer `unknown`, typed records, discriminated unions, and narrow type guards first.

## Preferred App Patterns

- Use Composition API and `<script setup lang="ts">` for app components.
- Avoid Options API in application code unless you are matching an existing local pattern or writing tests.
- Name components in `PascalCase`.
- Name composables with `useXxx`.
- Name stores with `useXxxStore` when practical.
- Keep page components focused on orchestration and rendering. Move reusable stateful logic into composables, stores, or utilities.
- Keep templates readable. Move complex expressions into computed values or helpers.
- Use stable IDs for `v-for` keys. Do not use array index keys for mutable lists.
- Do not mutate props directly. Emit state changes upward or clone into local state first.

## State Management

- Keep local UI state local when possible.
- Use composables for shared stateful logic across a focused part of the UI.
- Use Pinia for durable cross-route or cross-feature state such as auth, settings, and layout concerns.
- Use `storeToRefs()` when destructuring reactive store state.

## Performance Guidance

- Prefer `computed()` for derived values and `watch()` for side effects.
- Prefer `shallowRef()` for large payloads such as chat histories, tool traces, or chart configs when deep reactivity is unnecessary.
- Avoid expensive logic directly in templates.
- Profile before reaching for `v-memo`, `v-once`, or aggressive memoization patterns.

## Known Drift

- Some files are already much larger than the preferred target, especially route-level orchestration files.
- `ChatPage.vue` is an example of an oversized page component. When working in these files, prefer incremental extraction instead of broad reorganizations.
- Treat this document as guidance for new and modified code, not as a claim that the existing frontend fully complies today.

## Checks

```bash
cd frontend && bun run lint:check && bun run type-check
```
