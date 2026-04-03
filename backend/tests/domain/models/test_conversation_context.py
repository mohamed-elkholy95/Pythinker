from app.domain.models.conversation_context import TurnEventType, TurnRole


def test_turn_role_has_plan_and_thought():
    assert hasattr(TurnRole, "PLAN_SUMMARY")
    assert TurnRole.PLAN_SUMMARY.value == "plan_summary"
    assert hasattr(TurnRole, "THOUGHT")
    assert TurnRole.THOUGHT.value == "thought"


def test_turn_event_type_has_all_new_types():
    new_types = {
        "PLAN": "plan",
        "THOUGHT": "thought",
        "REFLECTION": "reflection",
        "VERIFICATION": "verification",
        "COMPREHENSION": "comprehension",
        "MODE_CHANGE": "mode_change",
        "TASK_RECREATION": "task_recreation",
    }
    for name, value in new_types.items():
        assert hasattr(TurnEventType, name), f"Missing TurnEventType.{name}"
        assert getattr(TurnEventType, name).value == value
