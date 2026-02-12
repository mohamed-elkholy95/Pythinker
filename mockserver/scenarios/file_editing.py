from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay

SAMPLE_PYTHON = '''"""
{description}
"""
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Application configuration."""
    name: str = "{name}"
    version: str = "1.0.0"
    debug: bool = False
    settings: dict = field(default_factory=dict)


def main() -> None:
    """Entry point."""
    config = Config()
    print(f"Starting {{config.name}} v{{config.version}}")

    # Initialize components
    setup_logging(config)
    run_app(config)


def setup_logging(config: Config) -> None:
    """Configure logging based on config."""
    import logging
    level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def run_app(config: Config) -> None:
    """Run the main application loop."""
    print(f"{{config.name}} is running...")
    # Application logic here


if __name__ == "__main__":
    main()
'''

async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    # Extract what they want to create
    topic = message.lower()
    for prefix in ["write", "create", "build", "make", "generate", "code"]:
        topic = topic.replace(prefix, "")
    topic = topic.strip()
    if not topic:
        topic = "a Python application"

    name = topic.replace(" ", "_")[:20]
    filename = f"{name}.py"

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "received", "message": "Understanding your request...",
    }
    await delay(0.5)

    yield "progress", {
        "event_id": eid(), "timestamp": ts(),
        "phase": "planning", "message": "Planning the implementation...",
        "estimated_steps": 2,
    }
    await delay(0.6)

    # Plan
    step1_id, step2_id = eid(), eid()
    yield "plan", {
        "event_id": eid(), "timestamp": ts(),
        "steps": [
            {"id": step1_id, "description": f"Create {filename}", "status": "pending", "event_id": eid(), "timestamp": ts()},
            {"id": step2_id, "description": "Verify and test the code", "status": "pending", "event_id": eid(), "timestamp": ts()},
        ],
    }
    await delay(0.3)

    # Step 1: Write file
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step1_id, "description": f"Create {filename}", "status": "running"}
    await delay(0.3)

    yield "thought", {
        "event_id": eid(), "timestamp": ts(),
        "status": "thinking", "thought_type": "analysis",
        "content": f"I'll create a well-structured Python file for {topic} with proper documentation and type hints.",
    }
    await delay(0.5)

    code = SAMPLE_PYTHON.replace("{description}", topic.title()).replace("{name}", name)
    tc1 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "file_write", "status": "calling",
        "function": "file_write",
        "args": {"file": f"/workspace/{filename}"},
        "display_command": f"Creating {filename}",
        "command_category": "file",
        "file_path": f"/workspace/{filename}",
    }
    await delay(1.0)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc1, "name": "file_write", "status": "called",
        "function": "file_write",
        "args": {"file": f"/workspace/{filename}"},
        "content": {"content": code},
        "file_path": f"/workspace/{filename}",
        "diff": "+" + code.replace("\n", "\n+"),
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step1_id, "description": f"Create {filename}", "status": "completed"}
    await delay(0.3)

    # Step 2: Verify
    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step2_id, "description": "Verify and test the code", "status": "running"}
    await delay(0.3)

    tc2 = tc()
    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "shell_exec", "status": "calling",
        "function": "shell_exec",
        "args": {"command": f"python -c 'import py_compile; py_compile.compile(\"/workspace/{filename}\", doraise=True)'"},
        "display_command": "Verifying syntax",
        "command_category": "shell",
        "command": f"python -c 'import py_compile; py_compile.compile(\"/workspace/{filename}\", doraise=True)'",
    }
    await delay(0.8)

    yield "tool", {
        "event_id": eid(), "timestamp": ts(),
        "tool_call_id": tc2, "name": "shell_exec", "status": "called",
        "function": "shell_exec",
        "args": {"command": f"python -c 'import py_compile; py_compile.compile(\"/workspace/{filename}\", doraise=True)'"},
        "content": {"console": [{"ps1": "user@sandbox:~$", "command": "python -c '...'", "output": ""}], "stdout": "", "exit_code": 0},
        "stdout": "", "exit_code": 0,
    }
    await delay(0.3)

    yield "step", {"event_id": eid(), "timestamp": ts(), "id": step2_id, "description": "Verify and test the code", "status": "completed"}
    await delay(0.3)

    yield "message", {
        "event_id": eid(), "timestamp": ts(),
        "content": f"I've created **{filename}** with a clean, well-structured implementation. The file includes:\n\n- Dataclass-based configuration\n- Type hints throughout\n- Logging setup\n- Clean entry point\n\nThe syntax has been verified and the code is ready to use.",
        "role": "assistant", "attachments": [],
    }
    await delay(0.2)

    yield "suggestion", {
        "event_id": eid(), "timestamp": ts(),
        "suggestions": [
            "Add unit tests for this code",
            "Add error handling and logging",
            "Create a requirements.txt",
        ],
    }

    yield "title", {
        "event_id": eid(), "timestamp": ts(),
        "title": f"Create: {topic.title()}"[:50],
    }

    yield "done", {"event_id": eid(), "timestamp": ts()}
