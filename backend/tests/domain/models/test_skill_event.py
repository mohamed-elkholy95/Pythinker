from app.domain.models.event import SkillEvent


def test_skill_event_creation():
    event = SkillEvent(
        skill_id="research-v1",
        skill_name="Research",
        action="activated",
        reason="Detected research task patterns",
    )
    assert event.type == "skill"
    assert event.skill_id == "research-v1"
    assert event.action == "activated"
    assert event.tools_affected is None


def test_skill_event_with_tools():
    event = SkillEvent(
        skill_id="coding-v1",
        skill_name="Coding",
        action="activated",
        reason="Step requires code execution",
        tools_affected=["shell_exec", "code_execute", "file_write"],
    )
    assert len(event.tools_affected) == 3


def test_skill_event_deactivated():
    event = SkillEvent(
        skill_id="research-v1",
        skill_name="Research",
        action="deactivated",
        reason="Step completed",
    )
    assert event.action == "deactivated"


def test_skill_event_serialization():
    event = SkillEvent(
        skill_id="browser-v1",
        skill_name="Browser Automation",
        action="matched",
        reason="URL pattern detected",
    )
    data = event.model_dump()
    assert data["type"] == "skill"
    assert "id" in data
    assert "timestamp" in data
