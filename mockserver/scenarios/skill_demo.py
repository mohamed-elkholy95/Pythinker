from __future__ import annotations
from typing import AsyncGenerator
from scenarios.engine import eid, ts, tc, delay


async def run(message: str, session_id: str) -> AsyncGenerator[tuple[str, dict], None]:
    yield (
        "progress",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "phase": "received",
            "message": "Activating skills...",
        },
    )
    await delay(0.5)

    # Skill activation
    yield (
        "skill_activation",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "skill_ids": ["skill_research", "skill_code_dev"],
            "skill_names": ["Deep Research", "Code Development"],
            "tool_restrictions": [
                "info_search_web",
                "browser_get_content",
                "file_write",
                "shell_exec",
            ],
            "prompt_chars": 1250,
        },
    )
    await delay(0.5)

    # Skill delivery
    yield (
        "skill_delivery",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "package_id": f"pkg_{eid()}",
            "name": "Custom Research Skill",
            "description": "A specialized skill for conducting targeted research with custom templates",
            "version": "1.0.0",
            "icon": "search",
            "category": "research",
            "author": "Pythinker",
            "file_tree": {
                "src": {
                    "main.py": {"type": "file", "path": "src/main.py", "size": 512},
                    "templates": {
                        "report.md": {
                            "type": "file",
                            "path": "src/templates/report.md",
                            "size": 256,
                        },
                    },
                },
                "config.json": {"type": "file", "path": "config.json", "size": 128},
            },
            "files": [
                {
                    "path": "src/main.py",
                    "content": "# Custom Research Skill\nimport json\n\ndef execute(query, options):\n    return {'status': 'success'}",
                    "size": 512,
                },
                {
                    "path": "src/templates/report.md",
                    "content": "# {title}\n\n## Summary\n{summary}\n\n## Details\n{details}",
                    "size": 256,
                },
                {
                    "path": "config.json",
                    "content": '{"name": "custom-research", "version": "1.0.0"}',
                    "size": 128,
                },
            ],
        },
    )
    await delay(0.5)

    # Now demonstrate the skill in action
    step_id = eid()
    yield (
        "plan",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "steps": [
                {
                    "id": step_id,
                    "description": "Execute skill-powered research",
                    "status": "pending",
                    "event_id": eid(),
                    "timestamp": ts(),
                },
            ],
        },
    )
    await delay(0.3)

    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step_id,
            "description": "Execute skill-powered research",
            "status": "running",
        },
    )
    await delay(0.3)

    tc1 = tc()
    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc1,
            "name": "info_search_web",
            "status": "calling",
            "function": "info_search_web",
            "args": {"query": "skill-based AI agent capabilities"},
            "display_command": "Skill-powered search",
            "command_category": "search",
        },
    )
    await delay(1.0)
    yield (
        "tool",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "tool_call_id": tc1,
            "name": "info_search_web",
            "status": "called",
            "function": "info_search_web",
            "args": {"query": "skill-based AI agent capabilities"},
            "content": {
                "results": [
                    {
                        "title": "AI Agent Skills Framework",
                        "link": "https://example.com/skills",
                        "snippet": "How skills enhance AI agent capabilities...",
                    }
                ],
                "query": "skill-based AI agent capabilities",
            },
        },
    )
    await delay(0.2)

    yield (
        "step",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "id": step_id,
            "description": "Execute skill-powered research",
            "status": "completed",
        },
    )
    await delay(0.3)

    yield (
        "message",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "content": "I've demonstrated the skill system:\n\n1. **Skill Activation**: Loaded the Deep Research and Code Development skills\n2. **Skill Delivery**: Delivered a custom research skill package with templates\n3. **Skill Execution**: Used the activated skills to perform a search\n\nSkills enhance my capabilities by providing specialized tools and templates for different tasks.",
            "role": "assistant",
            "attachments": [],
        },
    )
    await delay(0.2)

    yield (
        "suggestion",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "suggestions": [
                "Create a custom skill",
                "List all available skills",
                "Enable more skills",
            ],
        },
    )

    yield (
        "title",
        {
            "event_id": eid(),
            "timestamp": ts(),
            "title": "Skill System Demo",
        },
    )

    yield "done", {"event_id": eid(), "timestamp": ts()}
