# Installing Superpowers for Claude Code

## Option 1: Install from Marketplace (Recommended)

Run these commands in your Claude Code terminal:

```bash
# 1. Add the Superpowers marketplace
/plugin marketplace add obra/superpowers-marketplace

# 2. Install Superpowers from the marketplace
/plugin install superpowers@superpowers-marketplace

# 3. Verify installation
/help
```

You should see Superpowers commands like:
- `/superpowers:brainstorm` - Interactive design refinement
- `/superpowers:write-plan` - Create implementation plan
- `/superpowers:execute-plan` - Execute plan in batches

## Option 2: Install from Local Directory

Since you have `superpowers-main/` locally, you can link it:

```bash
# Create a symlink in Claude's plugins directory
ln -s /Users/panda/Desktop/Projects/pythinker/superpowers-main ~/.claude/plugins/cache/superpowers-local/superpowers/main

# Or copy the directory
cp -r /Users/panda/Desktop/Projects/pythinker/superpowers-main ~/.claude/plugins/cache/superpowers-local/superpowers/main
```

Then restart Claude Code.

## Verify Installation

After installation, test the skills:

```bash
# Check available commands
/help

# Use a skill
/superpowers:brainstorm
```

## Available Superpowers Commands

Once installed, you'll have access to:

### Design & Planning
- `/superpowers:brainstorm` - Interactive design refinement
- `/superpowers:write-plan` - Create implementation plans
- `/superpowers:execute-plan` - Execute plans in batches

### Development
- `/superpowers:test-driven-development` - RED-GREEN-REFACTOR cycle
- `/superpowers:systematic-debugging` - 4-phase root cause process
- `/superpowers:subagent-driven-development` - Subagent per task

### Git Workflow
- `/superpowers:using-git-worktrees` - Isolated workspaces
- `/superpowers:finishing-a-development-branch` - Merge/PR workflow

### Code Review
- `/superpowers:requesting-code-review` - Pre-review checklist
- `/superpowers:receiving-code-review` - Responding to feedback

### Meta
- `/superpowers:using-superpowers` - Introduction to the system
- `/superpowers:writing-skills` - Create new skills

## How to Use

### Manual Invocation
Start any message with the skill command:
```
/superpowers:brainstorm How should we architect the authentication system?
```

### Auto-Activation
Skills can also activate automatically based on your message content. The system will suggest relevant skills when appropriate.

## Troubleshooting

### Skills not appearing in /help
- Restart Claude Code
- Check plugin installation: `/plugin list`
- Re-install: `/plugin uninstall superpowers@superpowers-marketplace` then reinstall

### Commands not working
- Make sure to use the full command: `/superpowers:brainstorm` not just `/brainstorm`
- Check that the skill is enabled in settings

### Want shorter commands?
You can create aliases in your Claude Code settings or use the skill names directly once they're loaded.

## What You Get

Superpowers provides systematic workflows for:
- **TDD**: Write tests first, watch them fail, make them pass
- **Debugging**: 4-phase root cause investigation (no guessing!)
- **Planning**: Break work into 2-5 minute tasks
- **Code Review**: Systematic review against plan
- **Git Workflow**: Branch management and merge decisions

## Philosophy

- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success

## Learn More

- GitHub: https://github.com/obra/superpowers
- Blog Post: https://blog.fsck.com/2025/10/09/superpowers/
- Local Skills: `/Users/panda/Desktop/Projects/pythinker/superpowers-main/skills/`
