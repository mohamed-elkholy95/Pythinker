# Superpowers Skills Removal Design

**Date:** 2026-02-14
**Status:** Approved
**Approach:** Nuclear Clean - Complete Removal

---

## Overview

Complete removal of all 14 bundled Superpowers workflow skills, their infrastructure, command registry mappings, and documentation from Pythinker. This is a "nuclear clean" removal with zero preservation or migration.

### Scope

**What Gets Removed:**
- 14 Superpowers skills (brainstorming, TDD, debugging, etc.)
- Skill importer infrastructure (YAML frontmatter parser)
- Tool mapping system
- Command registry (all `/brainstorm`, `/tdd`, etc. commands)
- Startup seeding integration
- All superpowers-specific documentation

**What Remains Intact:**
- Core skill system (`OFFICIAL_SKILLS` in `skills_seed.py`)
- Official skills: research, coding, browser, file-management, data-analysis, etc.
- Built-in `skill-creator` meta-skill
- Skill infrastructure (Skill model, SkillService, skill routes)
- User-defined custom skills capability

### Impact Assessment

✓ **Zero User Impact:** Development mode, no production users
✓ **No Database Migration:** Skills in MongoDB auto-cleaned on next seed
✓ **Core Skill System Intact:** OFFICIAL_SKILLS remain functional
✓ **Skill Creator Intact:** Built-in skill-creator continues to work

Superpowers skills are cleanly separable because they:
1. Live in separate directory (`skills/`)
2. Use separate seeding path (not in `OFFICIAL_SKILLS`)
3. Have no dependencies from core agent logic

---

## Removal Strategy: Bottom-Up Approach

Delete in dependency order to prevent import errors and get clean compiler feedback at each step.

### Rationale

Bottom-up removal (data → infrastructure → docs) ensures:
- Clean linter/compiler feedback at each phase
- Easy verification that nothing breaks
- Natural progression from concrete (files) to abstract (docs)
- Matches "Simplicity First" principle from CLAUDE.md

---

## Phase 1: Remove Skill Files (Data Layer)

### Action
```bash
rm -rf backend/app/infrastructure/seeds/skills/
```

### What Gets Deleted
- All 14 skill directories with SKILL.md files
- Bundled resources (references/, scripts/, templates/)
- ~1000+ lines of skill definitions

### Skills Removed
1. brainstorming - Interactive design refinement
2. writing-plans - Create implementation plans
3. executing-plans - Execute plans in batches
4. test-driven-development - RED-GREEN-REFACTOR cycle
5. systematic-debugging - 4-phase root cause process
6. subagent-driven-development - Fast iteration with review
7. dispatching-parallel-agents - Concurrent subagent workflows
8. using-git-worktrees - Parallel development branches
9. finishing-a-development-branch - Merge/PR decision workflow
10. requesting-code-review - Pre-review checklist
11. receiving-code-review - Responding to feedback
12. verification-before-completion - Ensure fix works
13. using-superpowers - Introduction to skills system
14. writing-skills - Create new skills guide

### Verification
```bash
# Check for broken imports
ruff check backend/app/infrastructure/seeds/
```

---

## Phase 2: Remove Infrastructure

### Files to Delete
```bash
rm backend/app/infrastructure/seeds/superpowers_skills.py
rm backend/app/infrastructure/seeds/superpowers_importer.py
rm backend/app/infrastructure/seeds/superpowers_tool_mapping.py
rm backend/import_superpowers_skills.py
rm scripts/verify-bundled-skills.py
```

### File Descriptions
- `superpowers_skills.py` - Exports SUPERPOWERS_SKILLS list
- `superpowers_importer.py` - YAML frontmatter parser for SKILL.md files
- `superpowers_tool_mapping.py` - Default tool assignments per skill
- `import_superpowers_skills.py` - CLI script for skill import
- `verify-bundled-skills.py` - Validation script for bundled skills

### Verification
```bash
# Verify no orphaned imports
ruff check backend/
grep -r "superpowers_skills\|superpowers_importer\|superpowers_tool_mapping" backend/ --include="*.py"
# Expected: no matches
```

---

## Phase 3: Remove Documentation

### Files to Delete
```bash
rm SUPERPOWERS_CLAUDE_CODE_INTEGRATION.md
rm SUPERPOWERS_INTEGRATION_STATUS.md
rm INSTALL_SUPERPOWERS.md
rm docs/guides/SUPERPOWERS.md
rm backend/docs/plans/2026-02-02-superpowers-integration-mapping.md
```

### Verification
```bash
# Verify no broken doc links
grep -r "SUPERPOWERS\|superpowers" docs/ CLAUDE.md MEMORY.md AGENTS.md
# Review matches - should only be archive notes
```

---

## Phase 4: Code Modifications

### File 1: `backend/app/domain/services/command_registry.py`

**Remove:**
- `SUPERPOWERS_COMMANDS` list (lines 30-128)
- Loop in `_ensure_initialized()` that registers commands

**Keep:**
- `CommandMapping` dataclass
- `CommandRegistry` class and all methods
- Module-level singleton pattern
- Infrastructure for future custom commands

**Result:**
Empty command registry by default, but infrastructure intact for user-defined commands.

**Before:**
```python
SUPERPOWERS_COMMANDS: list[CommandMapping] = [
    CommandMapping(command="brainstorm", skill_id="brainstorming", ...),
    # ... 13 more commands
]

def _ensure_initialized(self) -> None:
    if self._initialized:
        return

    for mapping in SUPERPOWERS_COMMANDS:
        # Register commands...
```

**After:**
```python
# Empty by default - users can register custom commands via register_command()

def _ensure_initialized(self) -> None:
    if self._initialized:
        return

    self._initialized = True
    logger.info("CommandRegistry initialized (no default commands)")
```

---

### File 2: `CLAUDE.md`

**Remove:**
- Superpowers workflow references in Quick Reference
- `/brainstorm`, `/tdd`, `/debug` command examples
- Link to `docs/guides/SUPERPOWERS.md`
- "Superpowers Workflow" documentation section

**Keep:**
- Skill system documentation (skill-creator)
- All coding standards and development workflows
- Core skill references (research, coding, browser)

---

### File 3: `MEMORY.md`

**Remove:**
- Superpowers topic index entry
- Workflow pattern references to superpowers skills

**Keep:**
- All other memory topics and architectural patterns

---

### File 4: `AGENTS.md`

**Action:**
Check file for superpowers skill references and remove if present.

---

### File 5: `docs/_sidebar.md`

**Remove:**
- Link to `guides/SUPERPOWERS.md`

---

### File 6: `MIGRATION_SUMMARY.md`

**Add archive note:**
```markdown
## 2026-02-14: Superpowers Skills Removal

**Removed:**
- All 14 bundled superpowers workflow skills
- Command registry mappings (/brainstorm, /tdd, /debug, etc.)
- Superpowers-specific infrastructure and documentation

**Retained:**
- Core skill system (OFFICIAL_SKILLS in skills_seed.py)
- Built-in skill-creator for custom skill development
- Command registry infrastructure for future custom commands

**Rationale:**
Nuclear clean removal - architectural simplification during development phase.
```

---

## Testing & Verification Strategy

### Pre-Removal Verification
```bash
# Ensure clean starting state
cd backend
conda activate pythinker
ruff check . && ruff format --check .
pytest tests/
```

### Post-Removal Verification (After Each Phase)

**After Phase 1 (Skills Deleted):**
```bash
ruff check backend/app/infrastructure/seeds/
```

**After Phase 2 (Infrastructure Deleted):**
```bash
ruff check backend/
grep -r "superpowers_skills\|superpowers_importer\|superpowers_tool_mapping" backend/ --include="*.py"
# Expected: no matches
```

**After Phase 3 (Docs Deleted):**
```bash
grep -r "SUPERPOWERS\|superpowers" docs/ CLAUDE.md MEMORY.md AGENTS.md
# Review matches - should only be archive notes in MIGRATION_SUMMARY.md
```

**After Phase 4 (Code Updated):**
```bash
cd backend
ruff check . && ruff format --check .
pytest tests/domain/services/test_command_registry.py
pytest tests/
```

**Final Integration Test:**
```bash
./dev.sh up -d
docker logs pythinker-backend-1 --tail 50 | grep -i "skill\|error"
# Expected: "Seeded X official skills" (without superpowers)
```

### Expected Test Outcomes

✓ **Linting:** Zero errors, all imports resolve
✓ **Tests:** All pass (command_registry tests may need updates)
✓ **Startup:** Backend starts without superpowers skill seeding
✓ **Grep:** No lingering references (except archive notes)
✓ **Functionality:** Core skills (research, coding, browser) work normally

### Test Updates Required

**`tests/domain/services/test_command_registry.py`:**
- Update assertions if they check for specific superpowers commands
- Verify empty registry behavior
- Test custom command registration (if tested)

---

## Rollback Plan

In case of issues during removal:

1. **Git revert** - Single commit rollback
2. **Restore from backup** - If multi-commit removal
3. **Re-seed database** - Run `./dev.sh down -v && ./dev.sh up -d`

**Note:** Since we're in dev mode with no production users, rollback risk is minimal.

---

## Success Criteria

✅ All 14 superpowers skill directories deleted
✅ All infrastructure files deleted (5 files)
✅ All documentation files deleted (5 files)
✅ Command registry updated (no default commands)
✅ CLAUDE.md, MEMORY.md, AGENTS.md cleaned
✅ MIGRATION_SUMMARY.md updated with archive note
✅ All tests pass (ruff + pytest)
✅ Backend starts successfully
✅ No grep matches for superpowers references (except archive)
✅ Core skills remain functional

---

## Timeline

**Estimated Duration:** 1-2 hours

- Phase 1 (Skills): 10 minutes
- Phase 2 (Infrastructure): 15 minutes
- Phase 3 (Docs): 10 minutes
- Phase 4 (Code): 30 minutes
- Testing: 30 minutes
- Documentation: 15 minutes

---

## Risk Assessment

**Low Risk** - This is a clean removal because:
1. Superpowers skills are isolated (separate directory, separate seeding)
2. No production users affected (dev mode)
3. Core skill system untouched (OFFICIAL_SKILLS)
4. Database auto-cleans on next seed (no manual migration)
5. Full test coverage for verification

**Potential Issues:**
- Broken test assertions in `test_command_registry.py` (easily fixed)
- Lingering doc references (caught by grep)

**Mitigation:**
- Bottom-up approach ensures clean linter feedback
- Verification after each phase
- Git history allows instant rollback

---

## Post-Removal Considerations

### Future Skill Development

The core skill infrastructure remains intact:
- Users can still create custom skills via `skill-creator`
- Command registry can register custom commands programmatically
- Skill seeding system works for official and custom skills

### If Workflow Patterns Are Needed Later

Consider:
- Lightweight prompt templates instead of full skills
- Agent instructions in CLAUDE.md
- MCP tools for external workflows

---

## Conclusion

This design provides a systematic, low-risk approach to completely removing superpowers skills from Pythinker. The bottom-up removal strategy ensures clean feedback at each step, while comprehensive verification prevents regressions.

**Next Step:** Create implementation plan via `writing-plans` skill.
