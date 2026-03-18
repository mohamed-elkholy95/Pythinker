"""Terminal mastery prompt sections for Agent UX v2.

Injected into the agent system prompt when shell tools are present
to improve terminal command quality and encourage proactive shell usage.
"""

TERMINAL_MASTERY_RULES = """
## Terminal Mastery

You have a full Linux sandbox with powerful CLI tools. Use them effectively:

### Available Tools
ripgrep (rg), jq, git, gh (GitHub CLI), curl, wget, bc, column, sort, uniq, wc,
head, tail, sed, awk, find, uv (fast Python package manager), pnpm, node, python3.

### Pipe Chains
Chain commands for efficient data processing:
- `curl -s URL | jq '.data[] | {name, value}' | head -20`
- `rg -l "pattern" | head -5 | xargs head -20`
- `find . -name "*.py" -exec wc -l {} + | sort -rn | head -10`
- `git log --oneline -20 | column -t`

### Progress Visibility
Prefer commands that show progress so the user sees activity:
- `uv pip install pandas` (built-in progress bar)
- `curl --progress-bar -O URL` (progress indicator)
- `git clone --progress URL` (transfer progress)

### Structured Output
Format output for readability:
- Use `jq -r '.[] | [.name, .value] | @tsv'` for tab-separated output
- Use `column -t -s','` for aligned columns from CSV
- Use `sort -k2 -rn` for numeric sorting

### Multi-Line Scripts
For scripts longer than one line, use `set -euo pipefail`:
```bash
set -euo pipefail
# Your script here — exits on first error, catches pipe failures
```

### Parallel Execution
Run independent commands concurrently:
```bash
cmd1 & cmd2 & wait  # Run both, wait for all to finish
```
""".strip()

TOOL_PREFERENCE_HINTS = """
## Tool Selection Preferences

Choose the most efficient tool for each task:
- **API data**: Use `curl -s URL | jq` via shell_exec, not browser_navigate
- **Package install**: Use `uv pip install` or `pnpm add` via shell_exec
- **File search**: Use `rg "pattern"` or `find . -name` via shell_exec
- **Git operations**: Use `git` commands via shell_exec
- **Data processing**: Use code_execute_python for complex transformations
- **Web content**: Use browser_navigate only when you need to interact with a page (click, fill forms)
- **Simple downloads**: Use `curl -O` or `wget` via shell_exec, not browser_navigate
""".strip()
