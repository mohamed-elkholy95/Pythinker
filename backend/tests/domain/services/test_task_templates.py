"""Tests for task_templates: TaskTemplate, TemplateParameter, TemplateCategory, TASK_TEMPLATES."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.models.scheduled_task import (
    NotificationChannel,
    OutputDeliveryMethod,
    ScheduleType,
)
from app.domain.services.task_templates import (
    TASK_TEMPLATES,
    TaskTemplate,
    TemplateCategory,
    TemplateParameter,
)

# ── TemplateCategory enum ──────────────────────────────────────────────────


class TestTemplateCategory:
    def test_all_members_exist(self) -> None:
        names = {m.value for m in TemplateCategory}
        assert names == {"research", "monitoring", "reporting", "data", "content"}

    def test_string_comparison(self) -> None:
        assert TemplateCategory.RESEARCH == "research"
        assert TemplateCategory.MONITORING == "monitoring"


# ── TemplateParameter ──────────────────────────────────────────────────────


class TestTemplateParameter:
    def test_required_parameter_defaults(self) -> None:
        param = TemplateParameter(
            name="topics",
            description="Topics to search",
            param_type="string",
        )
        assert param.required is True
        assert param.default is None
        assert param.options is None
        assert param.placeholder is None

    def test_optional_parameter_with_default(self) -> None:
        param = TemplateParameter(
            name="count",
            description="Number of items",
            param_type="number",
            required=False,
            default=5,
        )
        assert param.required is False
        assert param.default == 5

    def test_select_parameter_with_options(self) -> None:
        param = TemplateParameter(
            name="format",
            description="Output format",
            param_type="select",
            options=["json", "csv", "html"],
        )
        assert param.options == ["json", "csv", "html"]


# ── TaskTemplate ───────────────────────────────────────────────────────────


class TestTaskTemplate:
    def _make_template(self, **kwargs) -> TaskTemplate:
        defaults = {
            "id": "test_template",
            "name": "Test Template",
            "description": "A test template",
            "category": TemplateCategory.RESEARCH,
            "task_prompt_template": "Search for {topics} and return {count} results",
        }
        defaults.update(kwargs)
        return TaskTemplate(**defaults)

    def test_default_values(self) -> None:
        tmpl = self._make_template()
        assert tmpl.icon == "calendar"
        assert tmpl.default_schedule_type == ScheduleType.DAILY
        assert tmpl.default_time_of_day == "09:00"
        assert tmpl.default_interval_seconds is None
        assert tmpl.suggested_output == OutputDeliveryMethod.SESSION
        assert tmpl.tags == []
        assert tmpl.parameters == []

    def test_generate_task_description_substitutes_placeholders(self) -> None:
        tmpl = self._make_template()
        result = tmpl.generate_task_description({"topics": "AI agents", "count": "5"})
        assert result == "Search for AI agents and return 5 results"

    def test_generate_task_description_list_values_joined(self) -> None:
        tmpl = self._make_template(
            task_prompt_template="Monitor {companies}",
        )
        result = tmpl.generate_task_description({"companies": ["Apple", "Google", "Microsoft"]})
        assert result == "Monitor Apple, Google, Microsoft"

    def test_generate_task_description_missing_placeholder_unchanged(self) -> None:
        tmpl = self._make_template()
        result = tmpl.generate_task_description({"topics": "AI"})
        assert "{count}" in result

    def test_create_scheduled_task_basic(self) -> None:
        tmpl = self._make_template(tags=["test", "research"])
        task = tmpl.create_scheduled_task(
            user_id="user-123",
            params={"topics": "ML", "count": "3"},
        )
        assert task.user_id == "user-123"
        assert "ML" in task.task_description
        assert task.schedule_type == ScheduleType.DAILY
        assert "template:test_template" in task.tags
        assert "test" in task.tags

    def test_create_scheduled_task_custom_name(self) -> None:
        tmpl = self._make_template()
        task = tmpl.create_scheduled_task(
            user_id="user-1",
            params={},
            name="My Custom Task",
        )
        assert task.name == "My Custom Task"

    def test_create_scheduled_task_default_name_includes_date(self) -> None:
        tmpl = self._make_template()
        task = tmpl.create_scheduled_task(user_id="u1", params={})
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert today in task.name

    def test_create_scheduled_task_custom_schedule_type(self) -> None:
        tmpl = self._make_template()
        task = tmpl.create_scheduled_task(
            user_id="u1",
            params={},
            schedule_type=ScheduleType.WEEKLY,
        )
        assert task.schedule_type == ScheduleType.WEEKLY

    def test_create_scheduled_task_default_notification(self) -> None:
        tmpl = self._make_template()
        task = tmpl.create_scheduled_task(user_id="u1", params={})
        assert NotificationChannel.IN_APP in task.notification_config.channels
        assert task.notification_config.notify_on_failure is True
        assert task.notification_config.notify_on_completion is False

    def test_create_scheduled_task_default_output(self) -> None:
        tmpl = self._make_template(suggested_output=OutputDeliveryMethod.FILE)
        task = tmpl.create_scheduled_task(user_id="u1", params={})
        assert task.output_config.delivery_method == OutputDeliveryMethod.FILE


# ── TASK_TEMPLATES registry ────────────────────────────────────────────────


class TestTaskTemplatesRegistry:
    def test_registry_is_not_empty(self) -> None:
        assert len(TASK_TEMPLATES) > 0

    def test_daily_news_digest_exists(self) -> None:
        assert "daily_news_digest" in TASK_TEMPLATES

    def test_competitor_monitoring_exists(self) -> None:
        assert "competitor_monitoring" in TASK_TEMPLATES

    def test_all_templates_have_valid_ids(self) -> None:
        for key, tmpl in TASK_TEMPLATES.items():
            assert tmpl.id == key, f"Template key '{key}' doesn't match id '{tmpl.id}'"

    def test_all_templates_have_non_empty_descriptions(self) -> None:
        for key, tmpl in TASK_TEMPLATES.items():
            assert tmpl.description, f"Template '{key}' has empty description"

    def test_all_templates_have_prompt_template(self) -> None:
        for key, tmpl in TASK_TEMPLATES.items():
            assert tmpl.task_prompt_template, f"Template '{key}' has empty prompt template"

    def test_daily_news_digest_has_topics_parameter(self) -> None:
        tmpl = TASK_TEMPLATES["daily_news_digest"]
        param_names = [p.name for p in tmpl.parameters]
        assert "topics" in param_names

    def test_daily_news_digest_category_is_research(self) -> None:
        tmpl = TASK_TEMPLATES["daily_news_digest"]
        assert tmpl.category == TemplateCategory.RESEARCH
