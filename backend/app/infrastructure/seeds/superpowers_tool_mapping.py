"""Tool name mapping between Superpowers references and Pythinker tools.

Superpowers skills reference tools conceptually ("read files", "run commands").
This module maps those concepts to Pythinker's actual tool names.
"""

# Pythinker tool names (from examining backend/app/domain/services/tools/)
PYTHINKER_TOOLS = {
    # File operations
    "file_read": "Read files from the workspace",
    "file_write": "Write files to the workspace",
    "file_edit": "Edit existing files",
    "file_list": "List directory contents",
    "file_search": "Search file contents (grep)",
    # Code operations
    "code_executor_run": "Execute Python code",
    "code_dev_analyze": "Analyze code structure",
    "repo_map_generate": "Generate repository map",
    # Shell operations
    "shell_execute": "Execute shell commands",
    # Git operations
    "git_status": "Get git status",
    "git_diff": "Get git diff",
    "git_commit": "Create git commit",
    "git_log": "Get git log",
    # Browser operations
    "browser_navigate": "Navigate to URL",
    "browser_get_content": "Get page content",
    "browser_agent_run": "Run browser agent",
    # Search operations
    "info_search_web": "Search the web",
    # Workspace operations
    "workspace_read_file": "Read file from workspace",
    "workspace_write_file": "Write file to workspace",
    # Scheduling
    "schedule_task": "Schedule background task",
}

# Mapping from Superpowers conceptual references to Pythinker tools
SUPERPOWERS_TO_PYTHINKER = {
    # File operations
    "read_file": "file_read",
    "write_file": "file_write",
    "edit_file": "file_edit",
    "list_files": "file_list",
    "search_code": "file_search",
    # Execution
    "execute_code": "code_executor_run",
    "execute_command": "shell_execute",
    "run_command": "shell_execute",
    "run_shell": "shell_execute",
    # Git operations (via shell)
    "git": "shell_execute",
    "git_commit": "git_commit",
    "git_diff": "git_diff",
    "git_status": "git_status",
    "git_log": "git_log",
    # Browser
    "browser": "browser_navigate",
    "browser_navigate": "browser_navigate",
    "browser_agent": "browser_agent_run",
    # Search
    "search": "info_search_web",
    "web_search": "info_search_web",
    # Analysis
    "analyze_code": "code_dev_analyze",
    "repo_map": "repo_map_generate",
}


def map_tool_name(superpowers_ref: str) -> str:
    """Map a Superpowers tool reference to a Pythinker tool name.

    Args:
        superpowers_ref: Tool reference from Superpowers skill

    Returns:
        Pythinker tool name, or original reference if no mapping exists
    """
    return SUPERPOWERS_TO_PYTHINKER.get(superpowers_ref, superpowers_ref)


def get_default_tools_for_skill(skill_name: str) -> list[str]:
    """Get default required tools for a Superpowers skill.

    Args:
        skill_name: Name of the skill

    Returns:
        List of Pythinker tool names
    """
    # Default tool sets by skill category
    common_tools = ["file_read", "file_write"]
    coding_tools = [*common_tools, "shell_execute"]
    planning_tools = [*common_tools, "file_list", "file_search"]
    debugging_tools = [*coding_tools, "file_search", "git_diff"]

    skill_tool_map = {
        # Planning & Design
        "brainstorming": planning_tools,
        "writing-plans": planning_tools,
        "executing-plans": coding_tools,
        # Development
        "test-driven-development": coding_tools,
        "systematic-debugging": debugging_tools,
        "subagent-driven-development": coding_tools,
        # Git workflows
        "using-git-worktrees": ["shell_execute", "git_status"],
        "finishing-a-development-branch": ["shell_execute", "git_status", "git_log"],
        # Code review
        "requesting-code-review": [*planning_tools, "file_search"],
        "receiving-code-review": coding_tools,
        # Orchestration
        "dispatching-parallel-agents": common_tools,
        # Verification
        "verification-before-completion": coding_tools,
        # Meta
        "using-superpowers": [],
        "writing-skills": common_tools,
    }

    return skill_tool_map.get(skill_name, common_tools)
