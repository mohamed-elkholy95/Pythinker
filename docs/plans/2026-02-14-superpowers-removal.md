# Superpowers Removal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Completely remove all 14 superpowers workflow skills, infrastructure, command registry mappings, and documentation from Pythinker.

**Architecture:** Bottom-up removal (data → infrastructure → docs → code) to ensure clean linter feedback at each step and prevent orphaned imports.

**Tech Stack:** Python, Ruff (linting), Pytest (testing), Git

---

## Pre-Flight Check

### Task 0: Verify Clean Starting State

**Step 1: Activate conda environment**

```bash
conda activate pythinker
```

Expected: `(pythinker)` prefix in shell prompt

**Step 2: Navigate to backend**

```bash
cd backend
```

**Step 3: Run linting**

```bash
ruff check . && ruff format --check .
```

Expected: No errors, all checks pass

**Step 4: Run tests**

```bash
pytest tests/
```

Expected: All tests pass (note: some may be skipped)

**Step 5: Verify current branch**

```bash
git branch --show-current
```

Expected: `main` or working branch name

---

## Phase 1: Remove Skill Files (Data Layer)

### Task 1: Delete Skills Directory

**Files:**
- Delete: `backend/app/infrastructure/seeds/skills/` (entire directory)

**Step 1: Verify directory exists**

```bash
ls -la backend/app/infrastructure/seeds/skills/
```

Expected: Shows 14 skill subdirectories

**Step 2: Delete skills directory**

```bash
rm -rf backend/app/infrastructure/seeds/skills/
```

Expected: No output (silent success)

**Step 3: Verify deletion**

```bash
ls backend/app/infrastructure/seeds/skills/ 2>&1
```

Expected: `ls: backend/app/infrastructure/seeds/skills/: No such file or directory`

**Step 4: Check for broken imports**

```bash
ruff check backend/app/infrastructure/seeds/
```

Expected: No errors (skills/ was leaf directory, no imports to it yet)

**Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove superpowers skill files directory

Delete all 14 bundled superpowers skills (brainstorming, TDD, debugging, etc.)
Phase 1/4 of nuclear clean removal.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows deletion of ~17 directories, 1 file changed (commit success)

---

## Phase 2: Remove Infrastructure Files

### Task 2: Delete Superpowers Infrastructure

**Files:**
- Delete: `backend/app/infrastructure/seeds/superpowers_skills.py`
- Delete: `backend/app/infrastructure/seeds/superpowers_importer.py`
- Delete: `backend/app/infrastructure/seeds/superpowers_tool_mapping.py`
- Delete: `backend/import_superpowers_skills.py`
- Delete: `scripts/verify-bundled-skills.py`

**Step 1: Delete infrastructure files**

```bash
rm backend/app/infrastructure/seeds/superpowers_skills.py
rm backend/app/infrastructure/seeds/superpowers_importer.py
rm backend/app/infrastructure/seeds/superpowers_tool_mapping.py
rm backend/import_superpowers_skills.py
rm scripts/verify-bundled-skills.py
```

Expected: No output (silent success)

**Step 2: Verify deletion**

```bash
ls backend/app/infrastructure/seeds/superpowers*.py 2>&1
ls backend/import_superpowers_skills.py 2>&1
ls scripts/verify-bundled-skills.py 2>&1
```

Expected: All return "No such file or directory"

**Step 3: Check for orphaned imports**

```bash
ruff check backend/
```

Expected: May show import errors if any files reference deleted modules

**Step 4: Search for import references**

```bash
grep -r "superpowers_skills\|superpowers_importer\|superpowers_tool_mapping" backend/ --include="*.py"
```

Expected: Should show no matches (or only in test files if any)

**Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove superpowers infrastructure files

Delete importer, tool mapping, and CLI script.
Phase 2/4 of nuclear clean removal.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows deletion of 5 files

---

## Phase 3: Remove Documentation Files

### Task 3: Delete Superpowers Documentation

**Files:**
- Delete: `SUPERPOWERS_CLAUDE_CODE_INTEGRATION.md`
- Delete: `SUPERPOWERS_INTEGRATION_STATUS.md`
- Delete: `INSTALL_SUPERPOWERS.md`
- Delete: `docs/guides/SUPERPOWERS.md`
- Delete: `backend/docs/plans/2026-02-02-superpowers-integration-mapping.md`

**Step 1: Delete documentation files**

```bash
rm SUPERPOWERS_CLAUDE_CODE_INTEGRATION.md
rm SUPERPOWERS_INTEGRATION_STATUS.md
rm INSTALL_SUPERPOWERS.md
rm docs/guides/SUPERPOWERS.md
rm backend/docs/plans/2026-02-02-superpowers-integration-mapping.md
```

Expected: No output (silent success)

**Step 2: Verify deletion**

```bash
ls SUPERPOWERS*.md 2>&1
ls INSTALL_SUPERPOWERS.md 2>&1
ls docs/guides/SUPERPOWERS.md 2>&1
```

Expected: All return "No such file or directory"

**Step 3: Check for broken doc links**

```bash
grep -r "SUPERPOWERS\|superpowers" docs/ CLAUDE.md MEMORY.md AGENTS.md | grep -v ".md~"
```

Expected: Shows remaining references (to be cleaned in Phase 4)

**Step 4: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: remove superpowers documentation files

Delete integration guides and status docs.
Phase 3/4 of nuclear clean removal.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows deletion of 5 documentation files

---

## Phase 4: Code Modifications

### Task 4: Update Command Registry

**Files:**
- Modify: `backend/app/domain/services/command_registry.py`

**Step 1: Read current file**

```bash
head -n 130 backend/app/domain/services/command_registry.py
```

Expected: Shows SUPERPOWERS_COMMANDS list (lines 30-128)

**Step 2: Create updated file (remove SUPERPOWERS_COMMANDS list)**

Edit `backend/app/domain/services/command_registry.py`:

- **Delete lines 29-128** (entire SUPERPOWERS_COMMANDS list and comment)
- **Update `_ensure_initialized()` method** around line 140

Replace:
```python
    def _ensure_initialized(self) -> None:
        """Ensure registry is initialized with Superpowers commands."""
        if self._initialized:
            return

        for mapping in SUPERPOWERS_COMMANDS:
            # Register primary command
            self._command_map[mapping.command] = mapping.skill_id
            self._skill_commands[mapping.skill_id] = mapping.command
            self._command_help[mapping.command] = mapping.description

            # Register aliases
            for alias in mapping.aliases:
                self._command_map[alias] = mapping.skill_id
                self._command_help[alias] = f"{mapping.description} (alias for /{mapping.command})"

        self._initialized = True
        logger.info(
            f"✓ CommandRegistry initialized with {len(SUPERPOWERS_COMMANDS)} commands "
            f"({len(self._command_map)} total including aliases)"
        )
```

With:
```python
    def _ensure_initialized(self) -> None:
        """Ensure registry is initialized (empty by default)."""
        if self._initialized:
            return

        self._initialized = True
        logger.info("✓ CommandRegistry initialized (no default commands)")
```

**Step 3: Verify linting**

```bash
cd backend
ruff check app/domain/services/command_registry.py
```

Expected: No errors

**Step 4: Format file**

```bash
ruff format app/domain/services/command_registry.py
```

Expected: No changes needed (or formatting applied)

**Step 5: Commit**

```bash
git add backend/app/domain/services/command_registry.py
git commit -m "$(cat <<'EOF'
refactor: remove superpowers commands from registry

Remove SUPERPOWERS_COMMANDS list. Registry infrastructure remains
for future custom commands, but starts empty by default.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of command_registry.py

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Read current superpowers references**

```bash
grep -n "superpowers\|Superpowers\|/brainstorm\|/tdd\|/debug" CLAUDE.md -i
```

Expected: Shows line numbers with superpowers references

**Step 2: Edit CLAUDE.md**

Remove the following sections/references:
- Any references to "Superpowers Workflow" in Quick Reference
- Command examples: `/brainstorm`, `/tdd`, `/debug`
- Link to `docs/guides/SUPERPOWERS.md`
- Any section titled "Superpowers" or similar

Keep:
- Skill system documentation (skill-creator)
- Core skill references
- All coding standards

**Step 3: Verify no broken links**

```bash
grep "SUPERPOWERS.md" CLAUDE.md
```

Expected: No matches

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: remove superpowers references from CLAUDE.md

Remove workflow references and command examples.
Core skill system documentation remains intact.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of CLAUDE.md

---

### Task 6: Update MEMORY.md

**Files:**
- Modify: `/Users/panda/.claude/projects/-Users-panda-Desktop-Projects-Pythinker/memory/MEMORY.md`

**Step 1: Read current superpowers references**

```bash
grep -n "superpowers\|Superpowers" /Users/panda/.claude/projects/-Users-panda-Desktop-Projects-Pythinker/memory/MEMORY.md -i
```

Expected: Shows line numbers with superpowers topic index

**Step 2: Edit MEMORY.md**

Remove:
- Superpowers topic index entry
- Workflow pattern references to superpowers skills

Keep:
- All other memory topics and architectural patterns

**Step 3: Commit memory changes**

```bash
cd /Users/panda/.claude/projects/-Users-panda-Desktop-Projects-Pythinker/memory/
git add MEMORY.md
git commit -m "$(cat <<'EOF'
docs: remove superpowers references from memory

Remove superpowers topic index and workflow references.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of MEMORY.md

---

### Task 7: Update AGENTS.md

**Files:**
- Check: `AGENTS.md`

**Step 1: Check for superpowers references**

```bash
grep -n "superpowers\|Superpowers" AGENTS.md -i
```

Expected: Shows matches if any exist

**Step 2: Edit AGENTS.md (if references found)**

Remove any superpowers skill references.

**Step 3: Commit if changes made**

```bash
git add AGENTS.md
git commit -m "$(cat <<'EOF'
docs: remove superpowers references from AGENTS.md

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification if file was changed

---

### Task 8: Update docs/_sidebar.md

**Files:**
- Modify: `docs/_sidebar.md`

**Step 1: Read current superpowers link**

```bash
grep -n "SUPERPOWERS" docs/_sidebar.md
```

Expected: Shows line with link to guides/SUPERPOWERS.md

**Step 2: Edit docs/_sidebar.md**

Remove line containing link to `guides/SUPERPOWERS.md`

**Step 3: Commit**

```bash
git add docs/_sidebar.md
git commit -m "$(cat <<'EOF'
docs: remove superpowers guide link from sidebar

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of docs/_sidebar.md

---

### Task 9: Update MIGRATION_SUMMARY.md

**Files:**
- Modify: `MIGRATION_SUMMARY.md`

**Step 1: Read current file end**

```bash
tail -n 20 MIGRATION_SUMMARY.md
```

Expected: Shows recent migration notes

**Step 2: Add archive note**

Append to MIGRATION_SUMMARY.md:

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

**Step 3: Commit**

```bash
git add MIGRATION_SUMMARY.md
git commit -m "$(cat <<'EOF'
docs: add superpowers removal to migration summary

Archive note for future reference.
Phase 4/4 of nuclear clean removal.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of MIGRATION_SUMMARY.md

---

## Phase 5: Testing & Verification

### Task 10: Run Full Backend Tests

**Step 1: Navigate to backend**

```bash
cd backend
```

**Step 2: Run linting**

```bash
ruff check . && ruff format --check .
```

Expected: Zero errors, all imports resolve

**Step 3: Run command registry tests**

```bash
pytest tests/domain/services/test_command_registry.py -v
```

Expected: Tests may fail if they assert specific superpowers commands exist
**If tests fail:** Update test file to expect empty registry

**Step 4: Run all tests**

```bash
pytest tests/
```

Expected: All tests pass (or only expected failures in command_registry tests)

**Step 5: Verify no orphaned imports**

```bash
grep -r "superpowers_skills\|superpowers_importer\|superpowers_tool_mapping" backend/ --include="*.py"
```

Expected: No matches

---

### Task 11: Fix Command Registry Tests (If Needed)

**Files:**
- Modify (if needed): `backend/tests/domain/services/test_command_registry.py`

**Step 1: Read test file**

```bash
cat backend/tests/domain/services/test_command_registry.py
```

Expected: Shows test assertions

**Step 2: Update tests if they check for superpowers commands**

If tests assert on specific commands (e.g., "brainstorm", "tdd"), update to:
- Test empty registry initialization
- Test custom command registration
- Remove assertions on superpowers commands

**Step 3: Run updated tests**

```bash
pytest tests/domain/services/test_command_registry.py -v
```

Expected: All tests pass

**Step 4: Commit test updates**

```bash
git add backend/tests/domain/services/test_command_registry.py
git commit -m "$(cat <<'EOF'
test: update command registry tests for empty default

Remove assertions on superpowers commands.
Test empty registry and custom command registration.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

Expected: Shows modification of test file

---

### Task 12: Integration Test (Backend Startup)

**Step 1: Start development stack**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
./dev.sh up -d
```

Expected: Containers start successfully

**Step 2: Check backend logs**

```bash
docker logs pythinker-backend-1 --tail 50 | grep -i "skill"
```

Expected: Should show "Seeded X official skills" (without superpowers count)
Should NOT show errors about missing superpowers modules

**Step 3: Check for errors**

```bash
docker logs pythinker-backend-1 --tail 100 | grep -i "error"
```

Expected: No errors related to superpowers or skills

**Step 4: Verify backend health**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"healthy"}` or similar

**Step 5: Stop stack**

```bash
./dev.sh down
```

Expected: Containers stop cleanly

---

## Phase 6: Final Verification

### Task 13: Comprehensive Grep Audit

**Step 1: Search for all superpowers references**

```bash
grep -r "SUPERPOWERS\|superpowers" . \
  --exclude-dir=node_modules \
  --exclude-dir=.git \
  --exclude-dir=__pycache__ \
  --exclude-dir=.pytest_cache \
  --exclude="*.pyc" \
  | grep -v "MIGRATION_SUMMARY.md" \
  | grep -v "2026-02-14-superpowers-removal-design.md" \
  | grep -v "2026-02-14-superpowers-removal.md"
```

Expected: No matches (except in migration docs and this plan)

**Step 2: Search backend Python files**

```bash
grep -r "superpowers" backend/ --include="*.py"
```

Expected: No matches

**Step 3: Search documentation**

```bash
grep -r "superpowers" docs/ CLAUDE.md README.md | grep -v "MIGRATION_SUMMARY"
```

Expected: No matches (except archive notes)

---

### Task 14: Final Test Suite Run

**Step 1: Clean test cache**

```bash
cd backend
rm -rf .pytest_cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

Expected: Cache directories removed

**Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass

**Step 3: Run linting**

```bash
ruff check . && ruff format --check .
```

Expected: Zero errors

**Step 4: Check test coverage (optional)**

```bash
pytest tests/ --cov=app --cov-report=term-missing
```

Expected: Coverage report shows no missing superpowers modules

---

## Success Criteria Checklist

**Verify all criteria met:**

```bash
# All skill directories deleted
[ ! -d "backend/app/infrastructure/seeds/skills" ] && echo "✅ Skills deleted" || echo "❌ Skills exist"

# All infrastructure files deleted
[ ! -f "backend/app/infrastructure/seeds/superpowers_skills.py" ] && echo "✅ Infrastructure deleted" || echo "❌ Infrastructure exists"

# All documentation files deleted
[ ! -f "SUPERPOWERS_CLAUDE_CODE_INTEGRATION.md" ] && echo "✅ Docs deleted" || echo "❌ Docs exist"

# Command registry updated (check for empty initialization)
grep -q "no default commands" backend/app/domain/services/command_registry.py && echo "✅ Registry updated" || echo "❌ Registry not updated"

# No orphaned imports
! grep -r "superpowers_skills\|superpowers_importer" backend/ --include="*.py" -q && echo "✅ No orphaned imports" || echo "❌ Orphaned imports found"

# Tests pass
cd backend && pytest tests/ -q && echo "✅ Tests pass" || echo "❌ Tests fail"
```

Expected: All checks show ✅

---

## Rollback Instructions

If critical issues arise:

```bash
# Option 1: Revert last N commits
git log --oneline -10
git revert <commit-hash>

# Option 2: Hard reset (DESTRUCTIVE - loses uncommitted changes)
git reset --hard HEAD~N

# Option 3: Full stack restart
./dev.sh down -v
./dev.sh up -d
```

---

## Completion

**Final Commit (After All Tasks):**

```bash
git log --oneline -15
# Review all commits from this plan

# Optional: Create summary commit if needed
git commit --allow-empty -m "$(cat <<'EOF'
refactor: complete superpowers removal (Phase 4/4)

Nuclear clean removal of all superpowers skills, infrastructure,
and documentation. Core skill system remains intact.

See docs/plans/2026-02-14-superpowers-removal-design.md for details.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

**Estimated Total Time:** 1-2 hours

**Task Count:** 14 tasks with 60+ individual steps
