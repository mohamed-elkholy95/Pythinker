# Superpowers Workflow System

Pythinker integrates the **Superpowers** workflow system by Jesse Vincent - a complete software development workflow built on composable skills. Superpowers provides structured, systematic approaches to common development tasks.

## Core Workflows

| Workflow | Command | When to Use |
|----------|---------|-------------|
| **Brainstorming** | `/brainstorm` | Before ANY creative work - creating features, building components, adding functionality |
| **Writing Plans** | `/write-plan` | After design approval - break work into bite-sized tasks (2-5 min each) |
| **Executing Plans** | `/execute-plan` | Implement plans in batches with checkpoints |
| **Test-Driven Development** | `/tdd` | When implementing features or fixing bugs - RED-GREEN-REFACTOR |
| **Systematic Debugging** | `/debug` | ANY bug, test failure, or unexpected behavior - 4-phase root cause process |
| **Subagent Development** | `/subagent` | Fast iteration with fresh subagent per task + two-stage review |
| **Git Worktrees** | `/worktree` | Create isolated workspace on new branch for parallel development |
| **Finishing Branch** | `/finish-branch` | Verify tests, present merge/PR options, clean up |
| **Code Review** | `/request-review` | Review code against plan before requesting review |
| **Verification** | `/verify` | Ensure fix/feature actually works before marking complete |

## Auto-Activation

Skills automatically activate based on message content:
- **"Let's build a feature"** → `brainstorming` activates
- **"Fix this bug"** → `systematic-debugging` activates
- **"Implement the login flow"** → `test-driven-development` activates
- **"Create a plan for X"** → `writing-plans` activates

## Command Invocation

Use `/command` syntax for explicit invocation:
```bash
/brainstorm  # Start design refinement
/write-plan  # Create implementation plan
/tdd         # Enable test-driven development
/debug       # Activate systematic debugging
```

## The Basic Workflow

### 1. Brainstorming (`/brainstorm`)
- Activates before writing code
- Refines rough ideas through questions
- Explores alternatives
- Presents design in sections for validation
- Saves design document to `docs/plans/YYYY-MM-DD-<topic>-design.md`

### 2. Writing Plans (`/write-plan`)
- Activates with approved design
- Breaks work into bite-sized tasks (2-5 minutes each)
- Every task has exact file paths, complete code, verification steps
- Saves plan to `docs/plans/YYYY-MM-DD-<feature-name>.md`

### 3. Executing Plans (`/execute-plan`)
- Activates with plan document
- Executes in batches with human checkpoints
- OR use subagent-driven-development for autonomous execution

### 4. Test-Driven Development (`/tdd`)
- Activates during implementation
- Enforces RED-GREEN-REFACTOR cycle
- Write failing test → Watch it fail → Write minimal code → Watch it pass → Commit
- NO production code without a failing test first

### 5. Systematic Debugging (`/debug`)
- Activates on bugs or test failures
- Phase 1: Root cause investigation (MUST complete before fixes)
- Phase 2: Pattern analysis
- Phase 3: Hypothesis and testing
- Phase 4: Implementation with failing test case

### 6. Code Review (`/request-review`)
- Reviews against plan
- Reports issues by severity
- Critical issues block progress

### 7. Verification (`/verify`)
- Ensures fix actually works
- Activates before marking tasks complete
- Verifies tests pass and behavior is correct

## Key Principles

- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Test-first always** - NO production code without a failing test first
- **Root cause first** - NO fixes without investigation
- **One question at a time** - Don't overwhelm with multiple questions
- **Incremental validation** - Present design in sections, validate each

## Integration with Pythinker

Superpowers skills are fully integrated into Pythinker's skill system:

- **MongoDB Storage**: Skills stored as OFFICIAL skills with source="official"
- **Auto-Trigger**: Skills activate automatically via trigger pattern matching
- **Command System**: `/command` syntax maps to skill invocations
- **Event Streaming**: `SkillActivationEvent` emitted when skills auto-trigger
- **Frontend UI**: Command palette (Cmd+K) for command discovery

## Available Commands Reference

| Category | Commands | Purpose |
|----------|----------|---------|
| **Design** | `/brainstorm`, `/design` | Interactive design refinement |
| **Planning** | `/write-plan`, `/plan`, `/create-plan` | Create implementation plans |
| **Execution** | `/execute-plan`, `/exec-plan` | Execute plans in batches |
| **Testing** | `/tdd`, `/test-first` | Test-driven development |
| **Debugging** | `/debug`, `/fix-bug` | Systematic debugging process |
| **Subagents** | `/subagent`, `/parallel` | Subagent orchestration |
| **Git** | `/worktree`, `/finish-branch` | Git workflow management |
| **Review** | `/request-review`, `/code-review` | Code review process |
| **Verification** | `/verify`, `/check` | Verify fixes and features |
| **Meta** | `/superpowers`, `/write-skill` | System help and skill creation |

## When Skills Activate

### Automatic Activation (AI-triggered based on message content)
- `test-driven-development` - When implementing features
- `systematic-debugging` - When encountering bugs/errors
- `verification-before-completion` - At task completion
- `brainstorming` - When creating new features
- `writing-plans` - When planning implementation

### Manual Invocation (User must explicitly request)
- `subagent-driven-development` - `/subagent` command
- `receiving-code-review` - `/receive-review` command
- `using-superpowers` - `/superpowers` command

### Both (AI or user can invoke)
- `brainstorming` - Auto on "build feature" OR `/brainstorm`
- `writing-plans` - Auto on "create plan" OR `/write-plan`
- `executing-plans` - Auto on "execute plan" OR `/execute-plan`
- `using-git-worktrees` - Auto on "create worktree" OR `/worktree`
- `finishing-a-development-branch` - Auto on "merge branch" OR `/finish-branch`
- `requesting-code-review` - Auto on "code review" OR `/request-review`
- `writing-skills` - Auto on "create skill" OR `/write-skill`

## Skill Content Location

Skills are imported from `superpowers-main/` directory and stored in MongoDB. Original content is in:
```
superpowers-main/
├── skills/
│   ├── brainstorming/SKILL.md
│   ├── writing-plans/SKILL.md
│   ├── test-driven-development/SKILL.md
│   ├── systematic-debugging/SKILL.md
│   └── [10 more skills...]
└── README.md
```

## Philosophy

- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success

## Important Notes

- Skills trigger automatically - you don't need to invoke them manually in most cases
- The agent checks for relevant skills before ANY task
- Mandatory workflows, not suggestions
- Follow skill instructions exactly - especially for TDD and debugging
