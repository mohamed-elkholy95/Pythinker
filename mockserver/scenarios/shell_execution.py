from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay

MOCK_OUTPUTS = {
    "ls": "total 24\ndrwxr-xr-x  5 user user 4096 Dec 20 10:00 .\ndrwxr-xr-x  3 user user 4096 Dec 20 09:00 ..\n-rw-r--r--  1 user user  256 Dec 20 10:00 main.py\n-rw-r--r--  1 user user  128 Dec 20 10:00 requirements.txt\ndrwxr-xr-x  2 user user 4096 Dec 20 10:00 src\ndrwxr-xr-x  2 user user 4096 Dec 20 10:00 tests",
    "pip": "Collecting package\n  Downloading package-1.0.0.tar.gz (15 kB)\nInstalling collected packages: package\nSuccessfully installed package-1.0.0",
    "python": "Hello, World!\nExecution completed successfully.",
    "npm": "added 150 packages in 3.2s\n\n25 packages are looking for funding\n  run `npm fund` for details",
    "git": "On branch main\nYour branch is up to date with 'origin/main'.\n\nnothing to commit, working tree clean",
    "default": "Command executed successfully.",
}

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    # Extract command from message
    cmd = message.lower()
    for prefix in ["run", "execute", "please"]:
        cmd = cmd.replace(prefix, "")
    cmd = cmd.strip()
    if not cmd:
        cmd = "ls -la"

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Preparing to execute command...",
    }
    await delay(0.4)

    # Determine mock output (check specific commands, skip "default" key)
    output = MOCK_OUTPUTS["default"]
    for key, val in MOCK_OUTPUTS.items():
        if key != "default" and key in cmd:
            output = val
            break

    step_id = eid()
    yield "plan", {
        "event_id": eid(), "timestamp": ts(),
        "steps": [
            {"id": step_id, "description": f"Execute: {cmd[:60]}", "status": "pending", "event_id": eid(), "timestamp": ts()},
        ],
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step_id, "description": f"Execute: {cmd[:60]}", "status": "running"}
    await delay(0.3)

    tc1 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "shell_exec", "status": "calling",
        "function": "shell_exec",
        "args": {"command": cmd},
        "display_command": f"Running: {cmd[:60]}",
        "command_category": "shell",
        "command": cmd,
    }
    await delay(1.2)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "shell_exec", "status": "called",
        "function": "shell_exec",
        "args": {"command": cmd},
        "content": {
            "console": [{"ps1": "user@sandbox:~$", "command": cmd, "output": output}],
            "stdout": output,
            "exit_code": 0,
        },
        "stdout": output, "exit_code": 0, "command": cmd,
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step_id, "description": f"Execute: {cmd[:60]}", "status": "completed"}
    await delay(0.3)

    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"The command `{cmd}` executed successfully with exit code 0.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.2)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            "Run another command",
            "View the output in detail",
            "Save the output to a file",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": f"Shell: {cmd[:40]}",
    }

    yield "done", {"event_id": eid(), "timestamp": ts()}
