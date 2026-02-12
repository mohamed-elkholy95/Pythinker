"""Task Templates for Common Recurring Tasks.

This module provides pre-built automation templates inspired by Pythinker's
automation capabilities. Users can quickly set up common recurring tasks
without manually configuring everything.

Available Templates:
- Daily News Digest
- Competitor Monitoring
- Price Tracking
- Report Generation
- Data Backup
- Social Media Monitoring
- Market Research
- Content Curation
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.domain.models.scheduled_task import (
    NotificationChannel,
    NotificationConfig,
    OutputConfig,
    OutputDeliveryMethod,
    ScheduleConfig,
    ScheduledTask,
    ScheduleType,
)


class TemplateCategory(str, Enum):
    """Categories for task templates."""

    RESEARCH = "research"
    MONITORING = "monitoring"
    REPORTING = "reporting"
    DATA = "data"
    CONTENT = "content"


@dataclass
class TemplateParameter:
    """Parameter definition for a template."""

    name: str
    description: str
    param_type: str  # string, number, boolean, list, select
    required: bool = True
    default: Any = None
    options: list[str] | None = None  # For select type
    placeholder: str | None = None


@dataclass
class TaskTemplate:
    """Template for creating scheduled tasks."""

    id: str
    name: str
    description: str
    category: TemplateCategory
    icon: str = "calendar"

    # Default schedule configuration
    default_schedule_type: ScheduleType = ScheduleType.DAILY
    default_time_of_day: str = "09:00"
    default_interval_seconds: int | None = None

    # Task prompt template (with {placeholder} for parameters)
    task_prompt_template: str = ""

    # Required parameters for the template
    parameters: list[TemplateParameter] = field(default_factory=list)

    # Suggested output configuration
    suggested_output: OutputDeliveryMethod = OutputDeliveryMethod.SESSION

    # Tags for organization
    tags: list[str] = field(default_factory=list)

    def generate_task_description(self, params: dict[str, Any]) -> str:
        """Generate the task description from template with parameters."""
        description = self.task_prompt_template
        for key, value in params.items():
            placeholder = f"{{{key}}}"
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            description = description.replace(placeholder, str(value))
        return description

    def create_scheduled_task(
        self,
        user_id: str,
        params: dict[str, Any],
        name: str | None = None,
        schedule_type: ScheduleType | None = None,
        scheduled_at: datetime | None = None,
        notification_config: NotificationConfig | None = None,
        output_config: OutputConfig | None = None,
    ) -> ScheduledTask:
        """Create a scheduled task from this template.

        Args:
            user_id: User creating the task
            params: Parameter values for the template
            name: Optional custom name (defaults to template name)
            schedule_type: Override default schedule type
            scheduled_at: When to first execute
            notification_config: Optional notification settings
            output_config: Optional output delivery settings

        Returns:
            A configured ScheduledTask ready for scheduling
        """
        # Generate task description from template
        task_description = self.generate_task_description(params)

        # Build schedule config
        schedule_config = ScheduleConfig(
            time_of_day=self.default_time_of_day,
        )

        # Default notification config
        if notification_config is None:
            notification_config = NotificationConfig(
                channels=[NotificationChannel.IN_APP],
                notify_on_failure=True,
                notify_on_completion=False,
            )

        # Default output config
        if output_config is None:
            output_config = OutputConfig(
                delivery_method=self.suggested_output,
            )

        return ScheduledTask(
            user_id=user_id,
            name=name or f"{self.name} - {datetime.now(UTC).strftime('%Y-%m-%d')}",
            task_description=task_description,
            schedule_type=schedule_type or self.default_schedule_type,
            scheduled_at=scheduled_at or datetime.now(UTC),
            interval_seconds=self.default_interval_seconds,
            schedule_config=schedule_config,
            notification_config=notification_config,
            output_config=output_config,
            tags=[*self.tags, f"template:{self.id}"],
        )


# Pre-built templates
TASK_TEMPLATES: dict[str, TaskTemplate] = {
    "daily_news_digest": TaskTemplate(
        id="daily_news_digest",
        name="Daily News Digest",
        description=(
            "Get a curated summary of news from specified topics or sources. "
            "Perfect for staying updated on industry trends or specific subjects."
        ),
        category=TemplateCategory.RESEARCH,
        icon="newspaper",
        default_schedule_type=ScheduleType.DAILY,
        default_time_of_day="08:00",
        task_prompt_template=(
            "Search for the latest news about {topics}. "
            "Focus on articles from the past 24 hours from reputable sources. "
            "Summarize the top {article_count} most relevant articles, including:\n"
            "- Article title and source\n"
            "- Brief 2-3 sentence summary\n"
            "- Why it's relevant\n"
            "Group articles by sub-topic if applicable. "
            "Conclude with key takeaways and emerging trends."
        ),
        parameters=[
            TemplateParameter(
                name="topics",
                description="Topics or keywords to search for",
                param_type="string",
                placeholder="AI agents, machine learning, automation",
            ),
            TemplateParameter(
                name="article_count",
                description="Number of articles to include",
                param_type="number",
                default=5,
                required=False,
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["news", "research", "daily"],
    ),
    "competitor_monitoring": TaskTemplate(
        id="competitor_monitoring",
        name="Competitor Monitoring",
        description=(
            "Monitor competitor websites, social media, and news mentions. "
            "Get alerts on product launches, pricing changes, and key announcements."
        ),
        category=TemplateCategory.MONITORING,
        icon="eye",
        default_schedule_type=ScheduleType.DAILY,
        default_time_of_day="09:00",
        task_prompt_template=(
            "Monitor the following competitors: {competitors}.\n\n"
            "Check for:\n"
            "1. Recent news mentions and press releases\n"
            "2. Social media activity and announcements\n"
            "3. Product or service updates\n"
            "4. Pricing changes (if publicly available)\n"
            "5. Job postings that indicate new initiatives\n\n"
            "Compare against our focus areas: {focus_areas}.\n"
            "Provide a summary report with actionable insights."
        ),
        parameters=[
            TemplateParameter(
                name="competitors",
                description="Competitor company names or URLs",
                param_type="string",
                placeholder="CompanyA, CompanyB, example.com",
            ),
            TemplateParameter(
                name="focus_areas",
                description="Areas to focus on for comparison",
                param_type="string",
                default="features, pricing, market positioning",
                required=False,
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["competitor", "monitoring", "intelligence"],
    ),
    "price_tracking": TaskTemplate(
        id="price_tracking",
        name="Price Tracking",
        description=(
            "Track prices of products across multiple websites. Get alerts when prices drop below a threshold."
        ),
        category=TemplateCategory.MONITORING,
        icon="tag",
        default_schedule_type=ScheduleType.DAILY,
        default_time_of_day="10:00",
        task_prompt_template=(
            "Check the current prices for the following products:\n"
            "{products}\n\n"
            "For each product:\n"
            "1. Visit the product page and extract the current price\n"
            "2. Note any discounts or promotions\n"
            "3. Compare with the target price threshold: ${price_threshold}\n"
            "4. Check availability status\n\n"
            "Generate a price report with:\n"
            "- Current prices vs previous (if available)\n"
            "- Products below threshold (HIGHLIGHT these)\n"
            "- Best deals and recommendations"
        ),
        parameters=[
            TemplateParameter(
                name="products",
                description="Product names or URLs to track",
                param_type="string",
                placeholder="Product 1 (https://...), Product 2 (https://...)",
            ),
            TemplateParameter(
                name="price_threshold",
                description="Target price threshold for alerts",
                param_type="number",
                default=100,
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["price", "tracking", "shopping"],
    ),
    "weekly_report": TaskTemplate(
        id="weekly_report",
        name="Weekly Report Generation",
        description=(
            "Generate a comprehensive weekly report based on data sources. "
            "Perfect for business metrics, project updates, or analytics summaries."
        ),
        category=TemplateCategory.REPORTING,
        icon="file-text",
        default_schedule_type=ScheduleType.WEEKLY,
        default_time_of_day="09:00",
        task_prompt_template=(
            "Generate a weekly report for: {report_topic}\n\n"
            "Report sections to include:\n"
            "1. Executive Summary (key highlights)\n"
            "2. {metrics} - with week-over-week comparisons\n"
            "3. Notable events or changes\n"
            "4. Challenges and blockers\n"
            "5. Recommendations and action items\n"
            "6. Outlook for next week\n\n"
            "Format the report in {format} format with clear headings and bullet points."
        ),
        parameters=[
            TemplateParameter(
                name="report_topic",
                description="Topic or project for the report",
                param_type="string",
                placeholder="Project X Progress, Marketing Metrics, etc.",
            ),
            TemplateParameter(
                name="metrics",
                description="Key metrics to include",
                param_type="string",
                default="KPIs, performance metrics, progress indicators",
            ),
            TemplateParameter(
                name="format",
                description="Report format",
                param_type="select",
                options=["Markdown", "HTML", "PDF"],
                default="Markdown",
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["report", "weekly", "summary"],
    ),
    "data_backup_check": TaskTemplate(
        id="data_backup_check",
        name="Data Backup Verification",
        description=("Verify data backup status and integrity. Ensures critical data is properly backed up."),
        category=TemplateCategory.DATA,
        icon="database",
        default_schedule_type=ScheduleType.DAILY,
        default_time_of_day="02:00",
        task_prompt_template=(
            "Perform a backup verification check for: {backup_targets}\n\n"
            "Verification steps:\n"
            "1. Check backup file existence and timestamps\n"
            "2. Verify file sizes are reasonable\n"
            "3. Test file integrity (checksums if available)\n"
            "4. Check backup storage space remaining\n"
            "5. Verify backup retention policy compliance\n\n"
            "Report any issues or warnings immediately."
        ),
        parameters=[
            TemplateParameter(
                name="backup_targets",
                description="Systems or directories to verify",
                param_type="string",
                placeholder="/backups/db, /backups/files",
            ),
        ],
        suggested_output=OutputDeliveryMethod.SESSION,
        tags=["backup", "data", "verification"],
    ),
    "social_monitoring": TaskTemplate(
        id="social_monitoring",
        name="Social Media Monitoring",
        description=(
            "Monitor social media for brand mentions, industry trends, "
            "or specific topics. Track sentiment and engagement."
        ),
        category=TemplateCategory.MONITORING,
        icon="share-2",
        default_schedule_type=ScheduleType.RECURRING,
        default_interval_seconds=14400,  # Every 4 hours
        task_prompt_template=(
            "Monitor social media for mentions of: {keywords}\n\n"
            "Platforms to check: {platforms}\n\n"
            "For each mention:\n"
            "1. Capture the post content and author\n"
            "2. Assess sentiment (positive/neutral/negative)\n"
            "3. Note engagement metrics (likes, shares, comments)\n"
            "4. Flag any urgent items requiring response\n\n"
            "Provide a summary with:\n"
            "- Total mentions by platform\n"
            "- Sentiment breakdown\n"
            "- Top influencer mentions\n"
            "- Recommended responses"
        ),
        parameters=[
            TemplateParameter(
                name="keywords",
                description="Keywords or brand names to monitor",
                param_type="string",
                placeholder="@company, #hashtag, brand name",
            ),
            TemplateParameter(
                name="platforms",
                description="Social platforms to monitor",
                param_type="string",
                default="Twitter, LinkedIn, Reddit",
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["social", "monitoring", "brand"],
    ),
    "market_research": TaskTemplate(
        id="market_research",
        name="Market Research Update",
        description=(
            "Gather and summarize market research on a specific industry or topic. "
            "Includes trends, statistics, and key insights."
        ),
        category=TemplateCategory.RESEARCH,
        icon="trending-up",
        default_schedule_type=ScheduleType.WEEKLY,
        default_time_of_day="10:00",
        task_prompt_template=(
            "Conduct market research on: {industry}\n\n"
            "Focus areas: {focus_areas}\n\n"
            "Research to include:\n"
            "1. Industry size and growth projections\n"
            "2. Key players and market share\n"
            "3. Recent trends and developments\n"
            "4. Emerging technologies or innovations\n"
            "5. Regulatory changes or considerations\n"
            "6. Consumer/buyer behavior insights\n\n"
            "Format as a structured report with sources cited."
        ),
        parameters=[
            TemplateParameter(
                name="industry",
                description="Industry or market to research",
                param_type="string",
                placeholder="AI agents, SaaS, healthcare tech",
            ),
            TemplateParameter(
                name="focus_areas",
                description="Specific areas to focus on",
                param_type="string",
                default="market size, competitors, trends",
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["market", "research", "analysis"],
    ),
    "content_curation": TaskTemplate(
        id="content_curation",
        name="Content Curation",
        description=(
            "Curate relevant content from specified sources for sharing or reference. "
            "Great for maintaining knowledge bases or content calendars."
        ),
        category=TemplateCategory.CONTENT,
        icon="bookmark",
        default_schedule_type=ScheduleType.DAILY,
        default_time_of_day="07:00",
        task_prompt_template=(
            "Curate content on: {topics}\n\n"
            "Sources to check: {sources}\n\n"
            "For each piece of content:\n"
            "1. Title and source\n"
            "2. Brief summary (2-3 sentences)\n"
            "3. Key takeaways\n"
            "4. Relevance score (1-10)\n"
            "5. Suggested use (sharing, reference, inspiration)\n\n"
            "Organize by topic and relevance. Include {content_count} best pieces."
        ),
        parameters=[
            TemplateParameter(
                name="topics",
                description="Topics to curate content for",
                param_type="string",
                placeholder="productivity, AI tools, industry news",
            ),
            TemplateParameter(
                name="sources",
                description="Content sources to check",
                param_type="string",
                default="industry blogs, news sites, social media",
            ),
            TemplateParameter(
                name="content_count",
                description="Number of pieces to include",
                param_type="number",
                default=10,
            ),
        ],
        suggested_output=OutputDeliveryMethod.FILE,
        tags=["content", "curation", "knowledge"],
    ),
}


def get_template(template_id: str) -> TaskTemplate | None:
    """Get a template by ID."""
    return TASK_TEMPLATES.get(template_id)


def get_templates_by_category(category: TemplateCategory) -> list[TaskTemplate]:
    """Get all templates in a category."""
    return [t for t in TASK_TEMPLATES.values() if t.category == category]


def list_all_templates() -> list[TaskTemplate]:
    """Get all available templates."""
    return list(TASK_TEMPLATES.values())


def search_templates(query: str) -> list[TaskTemplate]:
    """Search templates by name, description, or tags."""
    query_lower = query.lower()
    return [
        template
        for template in TASK_TEMPLATES.values()
        if (
            query_lower in template.name.lower()
            or query_lower in template.description.lower()
            or any(query_lower in tag for tag in template.tags)
        )
    ]
