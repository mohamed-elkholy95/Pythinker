# Claude Code Plugin & Skill Audit Report

**Date:** 2026-03-01
**Project:** Pythinker (AI Agent System)
**Stack:** FastAPI + Vue 3 + Docker + Python 3.12

---

## 1. Current Inventory

### Installed Plugins (12)

| # | Plugin | Source | Scope | Version | Enabled | Installs |
|---|--------|--------|-------|---------|---------|----------|
| 1 | feature-dev | claude-plugins-official | user | 55b58ec6 | Yes | 98,821 |
| 2 | security-guidance | claude-plugins-official | user | 55b58ec6 | Yes | 61,288 |
| 3 | code-simplifier | claude-plugins-official | user | 1.0.0 | Yes | 96,077 |
| 4 | explanatory-output-style | claude-plugins-official | user | 55b58ec6 | Yes | 26,545 |
| 5 | code-review | claude-plugins-official | user | 55b58ec6 | Yes | 117,748 |
| 6 | frontend-design | claude-code-plugins | user | 1.0.0 | Yes | — |
| 7 | **frontend-design** | **claude-plugins-official** | **project** | **55b58ec6** | **No** | **247,733** |
| 8 | vue-best-practices | vue-skills | user | f3dd1bf4 | Yes | — |
| 9 | vue-options-api-best-practices | vue-skills | user | f3dd1bf4 | Yes | — |
| 10 | python-development | ando-marketplace | user | 1.2.1 | Yes | — |
| 11 | **superpowers** | **claude-plugins-official** | **project** | **4.3.1** | **No** | **118,874** |
| 12 | superpowers | superpowers-marketplace | user | 4.3.1 | Yes | — |
| 13 | **typescript-lsp** | **claude-plugins-official** | **project** | **1.0.0** | **No** | **77,633** |

### MCP Servers (6 active)

| Server | Purpose | Config Source |
|--------|---------|--------------|
| claude-api-rotator | API key rotation | settings.json |
| context7 | Library documentation | CLI args |
| tavily | Web search/extract/crawl | CLI args |
| Ref | Documentation search | CLI args |
| chrome-devtools | Browser automation | CLI args |
| docker-mcp | Docker container management | CLI args |

### Custom Scripts (3)

| Script | Purpose |
|--------|---------|
| `~/.claude/statusline.sh` | Custom status line (model, tokens, cost) |
| `~/.claude/bin/nvm-npx` | NVM-aware npx wrapper for MCP |
| `~/.claude/bin/nvm-node` | NVM-aware node wrapper for MCP |

### Marketplaces (5)

| Marketplace | Source |
|-------------|--------|
| claude-plugins-official | anthropics/claude-plugins-official |
| claude-code-plugins | anthropics/claude-code.git |
| vue-skills | vuejs-ai/skills.git |
| ando-marketplace | kivilaid/plugin-marketplace.git |
| superpowers-marketplace | obra/superpowers-marketplace |

---

## 2. Redundancies Found

### CRITICAL: Duplicate superpowers (same version!)

```
superpowers@claude-plugins-official  → project scope, v4.3.1, 920K  (NOT enabled)
superpowers@superpowers-marketplace  → user scope,    v4.3.1, 1.3M  (ENABLED)
```

**Impact:** Two copies of 14 identical skills consuming 2.2MB total.
**Action:** Remove `superpowers@claude-plugins-official` (the disabled project-scope copy).

### CRITICAL: Duplicate frontend-design

```
frontend-design@claude-plugins-official  → project scope, 44K  (NOT enabled)
frontend-design@claude-code-plugins      → user scope,    32K  (ENABLED)
```

**Impact:** Two copies of the same frontend-design skill.
**Action:** Remove `frontend-design@claude-plugins-official` (the disabled project-scope copy).

### MODERATE: Installed but never enabled — typescript-lsp

```
typescript-lsp@claude-plugins-official → project scope, v1.0.0 (NOT enabled)
Contents: only a README.md
```

**Impact:** Dead weight. Was installed on 2026-02-09 and never enabled.
**Action:** Uninstall. The project uses Python + Vue (not TypeScript-only). Type checking is handled by `bun run type-check` and Vue TSC already.

### LOW: vue-options-api-best-practices — wrong paradigm

```
vue-options-api-best-practices@vue-skills → user scope (ENABLED)
```

**Impact:** Pythinker uses **Composition API** with `<script setup>` exclusively. Zero `.vue` files use Options API (verified by codebase grep — the 2 `export default {}` matches are locale config files, not Vue components).
**Action:** Disable or uninstall. The `vue-best-practices` plugin already covers Composition API patterns.

### LOW: MCP documentation overlap — context7 vs Ref

```
context7  → resolve-library-id → query-docs (structured library docs)
Ref       → ref_search_documentation → ref_read_url (web doc search)
```

**Impact:** Both serve documentation lookup. However, they have distinct strengths:
- **context7**: Library-specific versioned docs, code snippets, structured queries
- **Ref**: Broader web documentation search, arbitrary URL reading

**Action:** Keep both — they're complementary, not truly redundant. context7 is better for API reference, Ref is better for tutorials and guides.

### LOW: Blocklist contains stale test entry

```json
{"plugin": "code-review@claude-plugins-official", "reason": "just-a-test", "text": "This is a test #5"}
```

**Impact:** code-review is currently installed and enabled, but also exists in the blocklist from a test. This is contradictory.
**Action:** Clean up the blocklist entry.

---

## 3. Redundancy Removal Summary

| Action | Plugin | Savings |
|--------|--------|---------|
| **Uninstall** | `superpowers@claude-plugins-official` | 920K + 14 duplicate skills |
| **Uninstall** | `frontend-design@claude-plugins-official` | 44K + 1 duplicate skill |
| **Uninstall** | `typescript-lsp@claude-plugins-official` | README-only, dead weight |
| **Disable** | `vue-options-api-best-practices@vue-skills` | 80K, wrong paradigm for project |
| **Clean** | blocklist test entry for code-review | Removes stale contradictory entry |

**Total savings:** ~1.1MB cache, 16 duplicate skill/agent definitions eliminated, cleaner plugin resolution.

---

## 4. Suggested Enhancement Plugins

Based on Pythinker's stack (FastAPI + Vue 3 + Docker + Python 3.12 + Playwright) and the marketplace catalog:

### HIGH PRIORITY — Direct project benefit

| Plugin | Installs | Why |
|--------|----------|-----|
| **github** | 102,371 | PR management, issue tracking, code review workflows. Pythinker is on GitHub — this integrates directly. |
| **playwright** | 79,591 | Pythinker uses Playwright for browser automation in sandboxes. This plugin provides Playwright-specific testing patterns, debugging, and best practices. |
| **commit-commands** | 64,480 | Enhanced commit workflows. Pythinker CLAUDE.md mandates atomic commits by concern — this plugin enforces that discipline. |

### MEDIUM PRIORITY — Quality of life

| Plugin | Installs | Why |
|--------|----------|-----|
| **pyright-lsp** | 39,729 | Python type-checking LSP. Complements ruff (linting) with deeper type analysis. Pythinker enforces full type hints. |
| **hookify** | 22,399 | Easier hook creation/management. Pythinker CLAUDE.md references python_skill_activator and frontend_skill_activator hooks. |
| **claude-md-management** | 51,259 | CLAUDE.md is 400+ lines. This plugin helps maintain, validate, and organize project instructions. |

### LOW PRIORITY — Nice to have

| Plugin | Installs | Why |
|--------|----------|-----|
| **ralph-loop** | 83,061 | Autonomous task execution loop. Could complement superpowers for long-running tasks. |
| **serena** | 52,649 | Code understanding and navigation. Could complement feature-dev for large codebase exploration. |
| **huggingface-skills** | 10,390 | Pythinker is an AI/ML project. HuggingFace patterns could help with model integration. |
| **semgrep** | 2,477 | Advanced code security scanning. Complements security-guidance with pattern-based analysis. |

### NOT RECOMMENDED

| Plugin | Why Not |
|--------|---------|
| context7 plugin | Already have context7 MCP server active — the plugin would be redundant |
| agent-sdk-dev | For building Claude Agent SDK apps, not relevant to Pythinker's architecture |
| figma/figma-mcp | No Figma workflow in Pythinker |
| supabase | Pythinker uses MongoDB + Redis, not Supabase |
| Notion/slack/linear | No integration with these services |

---

## 5. MCP Server Optimization

### Current Setup Assessment

| Server | Status | Notes |
|--------|--------|-------|
| claude-api-rotator | Keep | Essential for API key rotation |
| context7 | Keep | Primary documentation source per CLAUDE.md |
| tavily | Keep | Web search, extract, crawl, research — heavily used |
| Ref | Keep | Complementary to context7 for broader web docs |
| chrome-devtools | Keep | Browser testing and debugging |
| docker-mcp | Keep | Docker container management for sandbox dev |

**Assessment:** All 6 MCP servers serve distinct purposes. No redundancy to remove.

### Suggested MCP Additions

| Server | Purpose | Why |
|--------|---------|-----|
| **qdrant-mcp** | Vector DB operations | Pythinker uses Qdrant for memory. Direct MCP access would speed development. |
| **redis-mcp** | Redis operations | Direct Redis inspection/debugging during development. |

---

## 6. Marketplace Optimization

### Current: 5 marketplaces

| Marketplace | Plugins Used | Assessment |
|-------------|-------------|------------|
| claude-plugins-official | 7 (3 disabled duplicates) | **Keep** — primary marketplace |
| claude-code-plugins | 1 (frontend-design) | **Review** — only 1 plugin, same as official |
| vue-skills | 2 (1 should be disabled) | **Keep** — Vue-specific skills |
| ando-marketplace | 1 (python-development) | **Keep** — Python skills |
| superpowers-marketplace | 1 (superpowers) | **Review** — duplicate of official |

**Recommendation:** After removing duplicate superpowers, consider whether `superpowers-marketplace` is needed separately from `claude-plugins-official`. Both provide the same v4.3.1. If the superpowers-marketplace receives updates faster, keep it. Otherwise, consolidate to the official marketplace copy.

Similarly, `claude-code-plugins` frontend-design may be the same as the official one — verify if there's a meaningful difference before keeping both marketplaces.

---

## 7. Quick Action Checklist

- [ ] Uninstall `superpowers@claude-plugins-official` (duplicate)
- [ ] Uninstall `frontend-design@claude-plugins-official` (duplicate)
- [ ] Uninstall `typescript-lsp@claude-plugins-official` (unused)
- [ ] Disable `vue-options-api-best-practices@vue-skills` (wrong paradigm)
- [ ] Clean blocklist test entry for code-review
- [ ] Install `github@claude-plugins-official` (high priority)
- [ ] Install `playwright@claude-plugins-official` (high priority)
- [ ] Install `commit-commands@claude-plugins-official` (high priority)
- [ ] Evaluate `pyright-lsp` and `claude-md-management` for medium-priority install
