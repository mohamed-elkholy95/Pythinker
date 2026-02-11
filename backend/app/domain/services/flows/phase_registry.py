"""Phase registry for the structured 6-phase agent flow.

Defines phase templates, complexity-based phase selection, and step-to-phase assignment.
"""

from __future__ import annotations

import re

from app.domain.models.plan import ExecutionStatus, Phase, PhaseType, Plan, StepType

# Phase template definitions with metadata for frontend rendering
PHASE_TEMPLATES: list[dict] = [
    {
        "phase_type": PhaseType.ALIGNMENT,
        "label": "Understanding Your Goal",
        "description": "Clarify objective, constraints, and depth level",
        "icon": "target",
        "color": "blue",
        "order": 1,
        "complexity_threshold": 0.0,  # Always included
        "step_hints": [
            "Clarify the research objective and success criteria",
        ],
        "default_step_type": StepType.ALIGNMENT,
    },
    {
        "phase_type": PhaseType.RESEARCH_FOUNDATION,
        "label": "Gathering & Verifying Information",
        "description": "Multi-source research with cross-validation",
        "icon": "search",
        "color": "purple",
        "order": 2,
        "complexity_threshold": 0.3,
        "step_hints": [
            "Search across credible sources and extract key claims",
            "Cross-validate claims and flag contradictions",
        ],
        "default_step_type": StepType.EXECUTION,
    },
    {
        "phase_type": PhaseType.ANALYSIS_SYNTHESIS,
        "label": "Analyzing Insights",
        "description": "Categorize findings, compare tradeoffs, identify patterns",
        "icon": "brain",
        "color": "amber",
        "order": 3,
        "complexity_threshold": 0.6,
        "step_hints": [
            "Analyze and categorize findings with tradeoff comparison",
            "Identify gaps, risks, and uncertainties",
        ],
        "default_step_type": StepType.EXECUTION,
    },
    {
        "phase_type": PhaseType.REPORT_GENERATION,
        "label": "Drafting the Report",
        "description": "Compose structured report with citations",
        "icon": "file-text",
        "color": "green",
        "order": 4,
        "complexity_threshold": 0.0,  # Always included
        "step_hints": [
            "Compose structured report with findings and recommendations",
        ],
        "default_step_type": StepType.EXECUTION,
    },
    {
        "phase_type": PhaseType.QUALITY_ASSURANCE,
        "label": "Quality Review",
        "description": "Fact-check, review reasoning, polish for clarity",
        "icon": "shield-check",
        "color": "orange",
        "order": 5,
        "complexity_threshold": 0.8,
        "step_hints": [
            "Verify factual claims against sources",
            "Review logical consistency and reasoning",
            "Polish for clarity and readability",
        ],
        "default_step_type": StepType.SELF_REVIEW,
    },
    {
        "phase_type": PhaseType.DELIVERY_FEEDBACK,
        "label": "Final Delivery",
        "description": "Deliver with confidence score and next actions",
        "icon": "send",
        "color": "emerald",
        "order": 6,
        "complexity_threshold": 0.0,  # Always included
        "step_hints": [
            "Deliver final report with confidence assessment",
        ],
        "default_step_type": StepType.DELIVERY,
    },
]


def select_phases_for_complexity(score: float) -> list[PhaseType]:
    """Select which phases to activate based on task complexity score.

    Args:
        score: Complexity score from 0.0 (trivial) to 1.0 (very complex)

    Returns:
        List of PhaseType values to activate, ordered by execution sequence
    """
    return [template["phase_type"] for template in PHASE_TEMPLATES if score >= template["complexity_threshold"]]


def build_phases(selected_types: list[PhaseType]) -> list[Phase]:
    """Build Phase objects from selected phase types.

    Args:
        selected_types: List of PhaseType values to instantiate

    Returns:
        List of Phase objects ready to be attached to a Plan
    """
    phases = [
        Phase(
            phase_type=template["phase_type"],
            label=template["label"],
            description=template["description"],
            icon=template["icon"],
            color=template["color"],
            order=template["order"],
            status=ExecutionStatus.PENDING,
        )
        for template in PHASE_TEMPLATES
        if template["phase_type"] in selected_types
    ]
    return sorted(phases, key=lambda p: p.order)


def get_phase_template(phase_type: PhaseType) -> dict | None:
    """Get the template for a specific phase type."""
    for template in PHASE_TEMPLATES:
        if template["phase_type"] == phase_type:
            return template
    return None


# Keyword patterns for auto-assigning steps to phases
_PHASE_KEYWORDS: dict[PhaseType, list[str]] = {
    PhaseType.ALIGNMENT: [
        r"clarif",
        r"understand",
        r"defin",
        r"objective",
        r"goal",
        r"requirement",
        r"scope",
        r"constraint",
    ],
    PhaseType.RESEARCH_FOUNDATION: [
        r"search",
        r"research",
        r"gather",
        r"find",
        r"collect",
        r"source",
        r"browse",
        r"investigate",
        r"cross.?validat",
        r"verify.*consistency",
        r"credib",
    ],
    PhaseType.ANALYSIS_SYNTHESIS: [
        r"analy[zs]",
        r"compar",
        r"categori",
        r"pattern",
        r"tradeoff",
        r"trade.?off",
        r"insight",
        r"gap",
        r"risk",
        r"uncertain",
        r"assess",
    ],
    PhaseType.REPORT_GENERATION: [
        r"draft",
        r"compos",
        r"write.*report",
        r"report",
        r"document",
        r"structur.*report",
        r"executive.*summary",
        r"compil",
    ],
    PhaseType.QUALITY_ASSURANCE: [
        r"fact.?check",
        r"verif.*claim",
        r"review.*reason",
        r"logical.*consist",
        r"polish",
        r"readab",
        r"quality",
        r"proofread",
    ],
    PhaseType.DELIVERY_FEEDBACK: [
        r"deliver",
        r"final",
        r"confidence.*score",
        r"present",
        r"submit",
        r"hand.?off",
    ],
}


def assign_steps_to_phases(plan: Plan) -> None:
    """Assign steps to phases based on step.phase_id or keyword heuristics.

    Steps that already have a phase_id are left unchanged.
    Steps without a phase_id are matched by keyword patterns.
    Unmatched steps are assigned to the most likely phase by position.

    Args:
        plan: Plan with steps and phases to link
    """
    if not plan.phases:
        return

    phase_by_type = {p.phase_type: p for p in plan.phases}
    active_types = [p.phase_type for p in sorted(plan.phases, key=lambda p: p.order)]

    for i, step in enumerate(plan.steps):
        # Skip already-assigned steps
        if step.phase_id:
            phase = plan.get_phase_by_id(step.phase_id)
            if phase and step.id not in phase.step_ids:
                phase.step_ids.append(step.id)
            continue

        # Try keyword matching
        desc_lower = step.description.lower()
        best_match: PhaseType | None = None
        best_score = 0

        for phase_type, patterns in _PHASE_KEYWORDS.items():
            if phase_type not in phase_by_type:
                continue
            score = sum(1 for p in patterns if re.search(p, desc_lower))
            if score > best_score:
                best_score = score
                best_match = phase_type

        if best_match and best_score > 0:
            phase = phase_by_type[best_match]
            step.phase_id = phase.id
            if step.id not in phase.step_ids:
                phase.step_ids.append(step.id)
            # Set step_type from template
            template = get_phase_template(best_match)
            if template:
                step.step_type = template["default_step_type"]
            continue

        # Fallback: assign by proportional position
        if active_types:
            position_ratio = i / max(len(plan.steps) - 1, 1)
            phase_index = min(int(position_ratio * len(active_types)), len(active_types) - 1)
            phase_type = active_types[phase_index]
            phase = phase_by_type[phase_type]
            step.phase_id = phase.id
            if step.id not in phase.step_ids:
                phase.step_ids.append(step.id)
            template = get_phase_template(phase_type)
            if template:
                step.step_type = template["default_step_type"]
