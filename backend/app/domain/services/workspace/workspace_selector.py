"""Workspace template selection based on task analysis."""
from typing import Optional
from app.domain.services.workspace.workspace_templates import (
    get_template,
    get_all_templates,
    WorkspaceTemplate,
)
import logging

logger = logging.getLogger(__name__)


class WorkspaceSelector:
    """Selects appropriate workspace template based on task description."""

    def select_template(self, task_description: str) -> WorkspaceTemplate:
        """Select best workspace template for task.

        Args:
            task_description: User's task description

        Returns:
            Best matching WorkspaceTemplate
        """
        task_lower = task_description.lower()

        # Score each template
        scores = {}
        for template in get_all_templates():
            score = 0
            for keyword in template.trigger_keywords:
                if keyword.lower() in task_lower:
                    score += 1
            scores[template.name] = score

        # Get highest scoring template
        if scores:
            best_template_name = max(scores, key=scores.get)
            best_score = scores[best_template_name]

            # If score > 0, use that template
            if best_score > 0:
                template = get_template(best_template_name)
                logger.info(f"Selected workspace template: {template.name} (score: {best_score})")
                return template

        # Default to research template
        logger.info("No specific template matched, using default: research")
        return get_template("research")
