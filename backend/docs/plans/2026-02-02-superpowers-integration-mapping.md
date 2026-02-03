# Superpowers Integration Mapping

**Date:** 2026-02-02
**Status:** In Progress

## Overview

This document maps Superpowers skills to Pythinker's Skill model, identifying field mappings, categories, icons, and trigger patterns for all 14 skills.

## Skill Model Mapping

### Direct Mappings

| Superpowers | Pythinker Skill Model | Notes |
|-------------|----------------------|-------|
| `name` (frontmatter) | `id` + `name` | Use name as slug for ID |
| `description` (frontmatter) | `description` | Direct copy |
| Full markdown content | `system_prompt_addition` | Everything after frontmatter |
| - | `category` | Inferred from skill content |
| - | `source` | Set to `SkillSource.OFFICIAL` |
| - | `icon` | Manually assigned Lucide icon |
| - | `author` | "Superpowers by Jesse Vincent" |

### Derived Fields

| Field | Derivation Strategy |
|-------|-------------------|
| `required_tools` | Extract tool names from skill content (search for tool references) |
| `optional_tools` | Parse optional tool mentions |
| `trigger_patterns` | Extract from description + skill content |
| `invocation_type` | Default to `BOTH` (user or AI can invoke) |
| `supports_dynamic_context` | Set to `False` initially |
| `allowed_tools` | Set to `None` (no restrictions) |

## Skill-by-Skill Mapping

### 1. brainstorming

| Field | Value |
|-------|-------|
| `id` | `brainstorming` |
| `name` | `Brainstorming` |
| `description` | You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation. |
| `category` | `CUSTOM` |
| `icon` | `lightbulb` |
| `required_tools` | `["read_file", "write_file", "execute_command"]` |
| `trigger_patterns` | `["(?i)create.*feature", "(?i)build.*component", "(?i)add.*functionality", "(?i)design\\s+", "(?i)implement.*new"]` |
| `invocation_type` | `BOTH` |

### 2. writing-plans

| Field | Value |
|-------|-------|
| `id` | `writing-plans` |
| `name` | `Writing Plans` |
| `description` | Use when you have a spec or requirements for a multi-step task, before touching code |
| `category` | `CUSTOM` |
| `icon` | `file-text` |
| `required_tools` | `["read_file", "write_file"]` |
| `trigger_patterns` | `["(?i)write.*plan", "(?i)create.*plan", "(?i)implementation.*plan", "(?i)break.*down.*tasks"]` |
| `invocation_type` | `BOTH` |

### 3. executing-plans

| Field | Value |
|-------|-------|
| `id` | `executing-plans` |
| `name` | `Executing Plans` |
| `description` | Execute implementation plans in batches with checkpoints |
| `category` | `CUSTOM` |
| `icon` | `play-circle` |
| `required_tools` | `["read_file", "write_file", "execute_command"]` |
| `trigger_patterns` | `["(?i)execute.*plan", "(?i)implement.*plan", "(?i)follow.*plan"]` |
| `invocation_type` | `BOTH` |

### 4. test-driven-development

| Field | Value |
|-------|-------|
| `id` | `test-driven-development` |
| `name` | `Test-Driven Development` |
| `description` | Use when implementing any feature or bugfix, before writing implementation code |
| `category` | `CODING` |
| `icon` | `check-circle` |
| `required_tools` | `["read_file", "write_file", "execute_command"]` |
| `trigger_patterns` | `["(?i)implement", "(?i)add.*feature", "(?i)write.*code", "(?i)build.*function"]` |
| `invocation_type` | `AI` (Auto-triggered, not user-invoked) |

### 5. systematic-debugging

| Field | Value |
|-------|-------|
| `id` | `systematic-debugging` |
| `name` | `Systematic Debugging` |
| `description` | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `category` | `CODING` |
| `icon` | `bug` |
| `required_tools` | `["read_file", "write_file", "execute_command", "search_code"]` |
| `trigger_patterns` | `["(?i)debug", "(?i)fix.*bug", "(?i)error", "(?i)test.*fail", "(?i)unexpected.*behavior"]` |
| `invocation_type` | `AI` (Auto-triggered) |

### 6. subagent-driven-development

| Field | Value |
|-------|-------|
| `id` | `subagent-driven-development` |
| `name` | `Subagent-Driven Development` |
| `description` | Dispatch fresh subagent per task with two-stage review (spec compliance, then code quality) |
| `category` | `CUSTOM` |
| `icon` | `users` |
| `required_tools` | `["read_file", "write_file", "execute_command"]` |
| `trigger_patterns` | `[]` (Manual invocation only) |
| `invocation_type` | `USER` |

### 7. dispatching-parallel-agents

| Field | Value |
|-------|-------|
| `id` | `dispatching-parallel-agents` |
| `name` | `Dispatching Parallel Agents` |
| `description` | Concurrent subagent workflows for parallel task execution |
| `category` | `CUSTOM` |
| `icon` | `git-branch` |
| `required_tools` | `["read_file", "write_file"]` |
| `trigger_patterns` | `[]` (Manual invocation only) |
| `invocation_type` | `USER` |

### 8. using-git-worktrees

| Field | Value |
|-------|-------|
| `id` | `using-git-worktrees` |
| `name` | `Using Git Worktrees` |
| `description` | Create isolated workspace on new branch for parallel development |
| `category` | `CODING` |
| `icon` | `git-branch` |
| `required_tools` | `["execute_command"]` |
| `trigger_patterns` | `["(?i)create.*worktree", "(?i)new.*branch", "(?i)isolat.*workspace"]` |
| `invocation_type` | `BOTH` |

### 9. finishing-a-development-branch

| Field | Value |
|-------|-------|
| `id` | `finishing-a-development-branch` |
| `name` | `Finishing a Development Branch` |
| `description` | Verify tests, present merge/PR options, clean up worktree |
| `category` | `CODING` |
| `icon` | `git-merge` |
| `required_tools` | `["execute_command", "read_file"]` |
| `trigger_patterns` | `["(?i)finish.*branch", "(?i)merge.*branch", "(?i)create.*pr", "(?i)pull.*request"]` |
| `invocation_type` | `BOTH` |

### 10. requesting-code-review

| Field | Value |
|-------|-------|
| `id` | `requesting-code-review` |
| `name` | `Requesting Code Review` |
| `description` | Review code against plan, report issues by severity before requesting review |
| `category` | `CODING` |
| `icon` | `file-search` |
| `required_tools` | `["read_file", "search_code"]` |
| `trigger_patterns` | `["(?i)code.*review", "(?i)review.*code", "(?i)ready.*review"]` |
| `invocation_type` | `BOTH` |

### 11. receiving-code-review

| Field | Value |
|-------|-------|
| `id` | `receiving-code-review` |
| `name` | `Receiving Code Review` |
| `description` | Respond to code review feedback systematically |
| `category` | `CODING` |
| `icon` | `message-square` |
| `required_tools` | `["read_file", "write_file"]` |
| `trigger_patterns` | `[]` (Manual invocation only) |
| `invocation_type` | `USER` |

### 12. verification-before-completion

| Field | Value |
|-------|-------|
| `id` | `verification-before-completion` |
| `name` | `Verification Before Completion` |
| `description` | Ensure the fix/feature is actually working before marking complete |
| `category` | `CODING` |
| `icon` | `check-square` |
| `required_tools` | `["execute_command", "read_file"]` |
| `trigger_patterns` | `[]` (Auto-triggered at task completion) |
| `invocation_type` | `AI` |

### 13. using-superpowers

| Field | Value |
|-------|-------|
| `id` | `using-superpowers` |
| `name` | `Using Superpowers` |
| `description` | Introduction to the Superpowers skills system |
| `category` | `CUSTOM` |
| `icon` | `zap` |
| `required_tools` | `[]` |
| `trigger_patterns` | `[]` (Manual invocation only) |
| `invocation_type` | `USER` |

### 14. writing-skills

| Field | Value |
|-------|-------|
| `id` | `writing-skills` |
| `name` | `Writing Skills` |
| `description` | Create new skills following best practices |
| `category` | `CUSTOM` |
| `icon` | `file-edit` |
| `required_tools` | `["read_file", "write_file"]` |
| `trigger_patterns` | `["(?i)create.*skill", "(?i)write.*skill", "(?i)new.*skill"]` |
| `invocation_type` | `BOTH` |

## Tool Name Mapping

### Pythinker Tool Names

Current Pythinker tools (from examining codebase):
- `browser` - Browser automation
- `search` - Web search
- `execute_code` - Python code execution
- `read_file` - File reading
- `write_file` - File writing
- `edit_file` - File editing
- `list_files` - Directory listing
- `search_code` - Code search (grep/ripgrep)
- `execute_command` - Shell command execution
- `git_*` - Git operations
- `schedule_task` - Task scheduling

### Superpowers References → Pythinker Tools

| Superpowers Reference | Pythinker Tool | Notes |
|----------------------|----------------|-------|
| "read files" | `read_file` | Direct mapping |
| "write files" | `write_file` | Direct mapping |
| "run commands" | `execute_command` | Shell execution |
| "search code" | `search_code` | Grep/ripgrep |
| "git operations" | `execute_command` | Git via shell |
| "run tests" | `execute_command` | Test runners via shell |
| "browser" | `browser` | Direct mapping |
| "web search" | `search` | Direct mapping |

## Category Assignment Strategy

| Category | Skills |
|----------|--------|
| `CODING` | test-driven-development, systematic-debugging, using-git-worktrees, finishing-a-development-branch, requesting-code-review, receiving-code-review, verification-before-completion |
| `CUSTOM` | brainstorming, writing-plans, executing-plans, subagent-driven-development, dispatching-parallel-agents, using-superpowers, writing-skills |

## Trigger Pattern Strategy

### Pattern Types

1. **Auto-activation patterns** - Trigger automatically when user input matches
2. **Manual-only patterns** - Empty list, requires explicit `/skill-name` invocation
3. **Completion patterns** - Trigger at end of tasks (verification-before-completion)

### Pattern Guidelines

- Use `(?i)` for case-insensitive matching
- Match intent, not exact phrases
- Prefer specific patterns over broad ones
- Test patterns against common user inputs

## Implementation Notes

### Dynamic Context Support

Initially set `supports_dynamic_context=False` for all skills. Future enhancement can add:
- `!command` substitution in skill content
- Dynamic workspace context injection
- Real-time file/directory listings

### Tool Restrictions

Initially set `allowed_tools=None` (no restrictions). Future enhancement can:
- Restrict TDD skill to only test-related tools
- Limit brainstorming to read/write (no execution)
- Enforce debugging tool subset

### Skill Dependencies

Some skills reference others:
- `writing-plans` → recommends `brainstorming` first
- `executing-plans` → requires `writing-plans` output
- `systematic-debugging` → uses `test-driven-development`

These can be modeled with a future `prerequisite_skills` field.

## Success Criteria

1. All 14 skills importable from SKILL.md format
2. Field mapping preserves intent and functionality
3. Categories enable proper organization in UI
4. Trigger patterns activate skills appropriately
5. Tool assignments enable skill functionality
6. Icons provide clear visual identification

## Next Steps

1. Implement `superpowers_importer.py` parser
2. Create `superpowers_skills.py` with all 14 skill definitions
3. Test import into MongoDB
4. Validate skill retrieval and activation
