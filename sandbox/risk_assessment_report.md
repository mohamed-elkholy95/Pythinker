# Risk Assessment Report for obra/superpowers Issues

## Overview
This report provides a risk assessment of the open issues in the obra/superpowers GitHub repository. The issues are categorized by their nature (bug, enhancement, question) and assessed for potential impact and likelihood.

## Open Issues

### Stop hook hangs indefinitely when Haiku API call times out - causes Claude Code to be stuck
- **Issue Type:** Bug
- **ID:** #390
- **Description:** The stop hook hangs indefinitely when the Haiku API call times out, causing Claude Code to become stuck.
- **Impact:** High - Directly affects the usability of Claude Code, leading to loss of productivity and potential data loss if work is not saved.
- **Likelihood:** Medium - API timeouts can be intermittent and depend on external service availability.
- **Risk Level:** High

### SessionStart hook fails on Windows — bash cannot resolve ${CLAUDE_PLUGIN_ROOT} path
- **Issue Type:** Bug
- **ID:** #389
- **Description:** The SessionStart hook fails on Windows because bash cannot resolve the ${CLAUDE_PLUGIN_ROOT} path.
- **Impact:** High - Prevents users on Windows from properly starting sessions, making the tool unusable on this platform.
- **Likelihood:** High - A consistent issue for Windows users due to path resolution problems.
- **Risk Level:** High

### Brainstorm skill: Use the AskUserQuestion tool
- **Issue Type:** Enhancement
- **ID:** #388
- **Description:** Suggests using the AskUserQuestion tool for the brainstorm skill.
- **Impact:** Low - This is an enhancement, not a bug, and its absence does not break existing functionality.
- **Likelihood:** N/A
- **Risk Level:** Low

### Automatic TDD Skill Enforcement Before Implementation
- **Issue Type:** Enhancement
- **ID:** #384
- **Description:** Proposes automatic TDD skill enforcement before implementation.
- **Impact:** Low - An enhancement that could improve code quality but is not critical for current operation.
- **Likelihood:** N/A
- **Risk Level:** Low

### 【opencode】Cannot use skill with /superpowers:brainstorming
- **Issue Type:** Bug
- **ID:** #381
- **Description:** Users are unable to use skills with /superpowers:brainstorming.
- **Impact:** Medium - Limits the functionality of the brainstorming feature, reducing its utility.
- **Likelihood:** Medium - If this is a consistent bug, it affects all users trying to use this specific skill.
- **Risk Level:** Medium

### Add E2E browser testing for web app development
- **Issue Type:** Enhancement
- **ID:** #374
- **Description:** Suggests adding end-to-end browser testing for web app development.
- **Impact:** Low - An enhancement that would improve testing but does not impact current user functionality directly.
- **Likelihood:** N/A
- **Risk Level:** Low

### TDD process is not followed and no tests were written - please help me understand why?
- **Issue Type:** Question
- **ID:** #373
- **Description:** A user is asking why the TDD process was not followed and no tests were written.
- **Impact:** Low - A question, not a functional issue. May indicate a need for better documentation or process communication.
- **Likelihood:** N/A
- **Risk Level:** Low

### [ BUG ]: There is an issue where the sub-agent cannot find the worktree location of the previous task when performing sub-agent-driven development.
- **Issue Type:** Bug
- **ID:** #371
- **Description:** The sub-agent cannot find the worktree location of the previous task during sub-agent-driven development.
- **Impact:** High - Breaks the continuity of sub-agent development, leading to significant workflow disruptions.
- **Likelihood:** Medium - If sub-agent driven development is a core feature, this is a critical bug.
- **Risk Level:** High

### [BUG] SessionStart hook shows 'hook error' on Windows when running alongside other plugins
- **Issue Type:** Bug
- **ID:** #369
- **Description:** The SessionStart hook shows a 'hook error' on Windows when running alongside other plugins.
- **Impact:** High - Similar to #389, this significantly impacts Windows users, especially those using multiple plugins, potentially rendering the tool unusable.
- **Likelihood:** High - A specific and likely reproducible bug for a segment of the user base.
- **Risk Level:** High

### v4.1.1 causing opencode start with blank screen
- **Issue Type:** Bug
- **ID:** #368
- **Description:** Version 4.1.1 causes opencode to start with a blank screen.
- **Impact:** Critical - Prevents users from using the application entirely.
- **Likelihood:** High - If tied to a specific version, it's a widespread and consistent issue for users of that version.
- **Risk Level:** Critical

### gemini cli & copilot instalation
- **Issue Type:** Enhancement
- **ID:** #358
- **Description:** Suggests installation improvements for Gemini CLI and Copilot.
- **Impact:** Low - An enhancement to the installation process, not a functional bug.
- **Likelihood:** N/A
- **Risk Level:** Low

### Claude Code plugin installation flaky due to name collision with claude-plugins-official (upstream bug)
- **Issue Type:** Bug
- **ID:** #355
- **Description:** Claude Code plugin installation is flaky due to a name collision with claude-plugins-official.
- **Impact:** Medium - Causes installation difficulties, leading to frustration and potential abandonment of the tool.
- **Likelihood:** Medium - An upstream bug that may require coordination to fix.
- **Risk Level:** Medium

### SessionStart hook produces no output on Windows (Git Bash shebang issue)
- **Issue Type:** Bug
- **ID:** #354
- **Description:** The SessionStart hook produces no output on Windows due to a Git Bash shebang issue.
- **Impact:** High - Affects Windows users' ability to get feedback from session starts, hindering debugging and operation.
- **Likelihood:** High - A specific issue tied to the Windows environment and Git Bash.
- **Risk Level:** High

### Install Superpowers to Oh my OpenCode
- **Issue Type:** Enhancement
- **ID:** #352
- **Description:** Suggests installing Superpowers to Oh my OpenCode.
- **Impact:** Low - An enhancement for integration, not a core functional issue.
- **Likelihood:** N/A
- **Risk Level:** Low

### Codex subagents use superpowers
- **Issue Type:** Bug
- **ID:** #350
- **Description:** Codex subagents are using superpowers. (This description is vague, assuming it implies an unintended or problematic usage).
- **Impact:** Medium - If this is unintended behavior, it could lead to unpredictable results or resource misuse. Further clarification is needed.
- **Likelihood:** Unknown - Needs more information to assess.
- **Risk Level:** Medium (pending clarification)

### make git worktree optional/removable
- **Issue Type:** Enhancement
- **ID:** #348
- **Description:** Proposes making git worktree optional/removable.
- **Impact:** Low - An enhancement for flexibility, not a critical bug.
- **Likelihood:** N/A
- **Risk Level:** Low

### Skill superpowers:brainstorm cannot be used with Skill tool due to disable-model-invocation
- **Issue Type:** Bug
- **ID:** #345
- **Description:** The 'superpowers:brainstorm' skill cannot be used with the Skill tool due to 'disable-model-invocation'.
- **Impact:** Medium - Limits the utility of the brainstorming skill, similar to #381.
- **Likelihood:** Medium - A specific functional limitation.
- **Risk Level:** Medium

### Make plan file save location configurable
- **Issue Type:** Enhancement
- **ID:** #337
- **Description:** Suggests making the plan file save location configurable.
- **Impact:** Low - An enhancement for user convenience, not a functional issue.
- **Likelihood:** N/A
- **Risk Level:** Low

### Droid (https://app.factory.ai/) support
- **Issue Type:** Enhancement
- **ID:** #324
- **Description:** Suggests adding support for Droid (https://app.factory.ai/).
- **Impact:** Low - An enhancement for integration with another tool.
- **Likelihood:** N/A
- **Risk Level:** Low

### Kiro CLI installation
- **Issue Type:** Enhancement
- **ID:** #319
- **Description:** Suggests improvements for Kiro CLI installation.
- **Impact:** Low - An enhancement to the installation process.
- **Likelihood:** N/A
- **Risk Level:** Low

### Redundant Subagent/Parallel Session prompt in Codex; clarify default in README.codex.md
- **Issue Type:** Enhancement
- **ID:** #315
- **Description:** Addresses redundant prompts and suggests clarifying defaults in README.codex.md.
- **Impact:** Low - User experience improvement, not a functional bug.
- **Likelihood:** N/A
- **Risk Level:** Low

### [opencode] How to have specify different models for different types of tasks?
- **Issue Type:** Question
- **ID:** #306
- **Description:** A user is asking how to specify different models for different types of tasks in opencode.
- **Impact:** Low - A question that may indicate a need for better documentation or a new feature.
- **Likelihood:** N/A
- **Risk Level:** Low

### Improve worktree UX: add optional guidance for caching and env setup
- **Issue Type:** Enhancement
- **ID:** #299
- **Description:** Suggests improving worktree UX with guidance for caching and environment setup.
- **Impact:** Low - An enhancement for user experience.
- **Likelihood:** N/A
- **Risk Level:** Low

### Cursor IDE compatibility
- **Issue Type:** Enhancement
- **ID:** #295
- **Description:** Suggests improving compatibility with Cursor IDE.
- **Impact:** Low - An enhancement for integration with another IDE.
- **Likelihood:** N/A
- **Risk Level:** Low

### every time before brainstorm asking to confirm, claude code will popup a cmd window
- **Issue Type:** Bug
- **ID:** #293
- **Description:** Before brainstorming, Claude Code pops up a command window every time, asking for confirmation.
- **Impact:** Medium - Disrupts user workflow with unnecessary interruptions.
- **Likelihood:** Medium - If this is a consistent behavior, it affects all users of the brainstorming feature.
- **Risk Level:** Medium

## Summary of Risks

The most critical risks identified are:
- **v4.1.1 causing opencode start with blank screen (#368):** This is a critical bug that prevents the application from starting, rendering it unusable.
- **SessionStart hook failures on Windows (#389, #369, #354):** These issues severely impact Windows users, preventing proper session initiation and feedback, making the tool difficult or impossible to use on this platform.
- **Sub-agent worktree location issue (#371):** This bug disrupts the core functionality of sub-agent driven development, leading to significant workflow problems.
- **Haiku API call timeout leading to Claude Code stuck (#390):** This issue directly impacts the usability and stability of Claude Code, causing productivity loss.

## Recommendations

1.  **Prioritize Critical Bugs:** Immediately address issues #368, #389, #369, #354, #371, and #390. These are critical for the basic functionality and usability of the product, especially for Windows users.
2.  **Improve Windows Compatibility:** Investigate and resolve the root causes of the recurring SessionStart hook failures and path resolution issues on Windows.
3.  **Enhance Documentation:** For questions like #373 and #306, consider updating documentation or providing clearer guidance on processes and configurations.
4.  **Review Enhancement Requests:** Evaluate enhancement requests like #388, #384, #374, etc., for future development cycles based on user demand and strategic alignment.
5.  **Clarify Vague Issues:** Get more details for vague issues like #350 ("Codex subagents use superpowers") to properly assess their impact and priority.
