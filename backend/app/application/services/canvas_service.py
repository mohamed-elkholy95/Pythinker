"""Application service for canvas project management."""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.models.canvas import (
    CanvasElement,
    CanvasPage,
    CanvasProject,
    CanvasVersion,
    ElementType,
)
from app.infrastructure.external.image_generation import get_image_generation_service
from app.infrastructure.external.llm import get_llm
from app.infrastructure.repositories.mongo_canvas_repository import MongoCanvasRepository

logger = logging.getLogger(__name__)


class CanvasAddOperation(BaseModel):
    action: Literal["add"] = "add"
    element_type: ElementType
    x: float
    y: float
    width: float
    height: float
    fill_color: str | None = None
    text: str | None = None
    font_size: float | None = None
    src: str | None = None
    opacity: float | None = None
    corner_radius: float | None = None
    name: str | None = None


class CanvasModifyOperation(BaseModel):
    action: Literal["modify"] = "modify"
    element_id: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    rotation: float | None = None
    opacity: float | None = None
    text: str | None = None
    fill_color: str | None = None
    font_size: float | None = None


class CanvasDeleteOperation(BaseModel):
    action: Literal["delete"] = "delete"
    element_ids: list[str] = Field(default_factory=list)


class CanvasArrangeOperation(BaseModel):
    action: Literal["arrange"] = "arrange"
    element_id: str
    direction: Literal["bring_to_front", "send_to_back"]


CanvasEditOperation = Annotated[
    CanvasAddOperation | CanvasModifyOperation | CanvasDeleteOperation | CanvasArrangeOperation,
    Field(discriminator="action"),
]


class CanvasEditPlan(BaseModel):
    operations: list[CanvasEditOperation] = Field(default_factory=list)
    notes: str | None = None


class CanvasService:
    """Service for managing canvas projects, versions, and AI operations."""

    def __init__(
        self,
        canvas_repo: MongoCanvasRepository | None = None,
    ) -> None:
        self._repo = canvas_repo or MongoCanvasRepository()
        self._llm = get_llm()

    # --- Project CRUD ---

    async def create_project(
        self,
        user_id: str,
        name: str = "Untitled Design",
        width: float = 1920.0,
        height: float = 1080.0,
        background: str = "#FFFFFF",
        session_id: str | None = None,
    ) -> CanvasProject:
        """Create a new canvas project with a default page."""
        page = CanvasPage(
            id=str(uuid.uuid4()),
            name="Page 1",
            width=width,
            height=height,
            background=background,
        )
        project = CanvasProject(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            name=name,
            width=width,
            height=height,
            background=background,
            pages=[page],
        )
        return await self._repo.save(project)

    async def get_project(self, project_id: str) -> CanvasProject | None:
        return await self._repo.find_by_id(project_id)

    async def list_projects(
        self, user_id: str, skip: int = 0, limit: int = 50
    ) -> list[CanvasProject]:
        return await self._repo.find_by_user_id(user_id, skip=skip, limit=limit)

    async def update_project(
        self, project_id: str, project: CanvasProject
    ) -> CanvasProject | None:
        """Update a project (full state save). Auto-saves a version."""
        existing = await self._repo.find_by_id(project_id)
        if not existing:
            return None

        # Auto-save version before overwriting
        settings = get_settings()
        version_count = await self._repo.count_versions(project_id)
        if version_count < settings.canvas_max_versions:
            version = CanvasVersion(
                id=str(uuid.uuid4()),
                project_id=project_id,
                version=existing.version,
                name=f"Auto-save v{existing.version}",
                pages=existing.pages,
            )
            await self._repo.save_version(version)

        project.version = existing.version + 1
        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project_id, project)

    async def delete_project(self, project_id: str) -> bool:
        return await self._repo.delete(project_id)

    # --- Version management ---

    async def get_versions(
        self, project_id: str, limit: int = 20
    ) -> list[CanvasVersion]:
        return await self._repo.get_versions(project_id, limit=limit)

    async def restore_version(
        self, project_id: str, version: int
    ) -> CanvasProject | None:
        """Restore a project to a previous version."""
        project = await self._repo.find_by_id(project_id)
        if not project:
            return None

        version_obj = await self._repo.get_version(project_id, version)
        if not version_obj:
            return None

        # Save current state as a version first
        settings = get_settings()
        version_count = await self._repo.count_versions(project_id)
        if version_count < settings.canvas_max_versions:
            save_version = CanvasVersion(
                id=str(uuid.uuid4()),
                project_id=project_id,
                version=project.version,
                name=f"Before restore to v{version}",
                pages=project.pages,
            )
            await self._repo.save_version(save_version)

        # Restore pages from version
        project.pages = version_obj.pages
        project.version = project.version + 1
        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project_id, project)

    # --- Element operations ---

    async def add_element(
        self,
        project_id: str,
        element: CanvasElement,
        page_index: int = 0,
    ) -> CanvasProject | None:
        """Add an element to a page."""
        project = await self._repo.find_by_id(project_id)
        if not project or page_index >= len(project.pages):
            return None

        settings = get_settings()
        if len(project.pages[page_index].elements) >= settings.canvas_max_elements:
            raise ValueError(f"Maximum {settings.canvas_max_elements} elements per page")

        project.pages[page_index].elements.append(element)
        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project_id, project)

    async def modify_element(
        self,
        project_id: str,
        element_id: str,
        updates: dict[str, Any],
    ) -> CanvasProject | None:
        """Modify element properties."""
        project = await self._repo.find_by_id(project_id)
        if not project:
            return None

        for page in project.pages:
            for i, el in enumerate(page.elements):
                if el.id == element_id:
                    el_dict = el.model_dump()
                    el_dict.update(updates)
                    page.elements[i] = CanvasElement.model_validate(el_dict)
                    project.updated_at = datetime.now(UTC)
                    return await self._repo.update(project_id, project)

        return None

    async def delete_elements(
        self, project_id: str, element_ids: list[str]
    ) -> CanvasProject | None:
        """Delete elements by IDs."""
        project = await self._repo.find_by_id(project_id)
        if not project:
            return None

        ids_set = set(element_ids)
        for page in project.pages:
            page.elements = [el for el in page.elements if el.id not in ids_set]

        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project_id, project)

    # --- AI operations ---

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
    ) -> list[str]:
        """Generate image via fal.ai FLUX. Returns image URLs."""
        service = get_image_generation_service()
        if not service.is_configured:
            raise ValueError("Image generation not configured (FAL_API_KEY missing)")
        return await service.generate_image(prompt, width, height)

    async def edit_image(self, image_url: str, instruction: str) -> list[str]:
        """Edit image via NL instruction. Returns processed image URLs."""
        service = get_image_generation_service()
        if not service.is_configured:
            raise ValueError("Image generation not configured (FAL_API_KEY missing)")
        return await service.edit_image(image_url, instruction)

    async def remove_background(self, image_url: str) -> list[str]:
        """Remove image background. Returns processed image URLs."""
        service = get_image_generation_service()
        if not service.is_configured:
            raise ValueError("Image generation not configured (FAL_API_KEY missing)")
        return await service.remove_background(image_url)

    async def apply_ai_edit(
        self,
        project_id: str,
        instruction: str,
    ) -> CanvasProject | None:
        """Apply a natural language edit to the canvas.

        Uses LLM to parse instruction into structured element operations,
        then applies them to the project.
        """
        project = await self._repo.find_by_id(project_id)
        if not project:
            return None

        llm = self._llm or get_llm()
        if not llm:
            logger.warning("AI edit requested but no LLM configured.")
            return None
        self._llm = llm

        page = project.pages[0] if project.pages else None
        context = {
            "project": {
                "id": project.id,
                "name": project.name,
            },
            "page": {
                "id": page.id if page else None,
                "width": page.width if page else project.width,
                "height": page.height if page else project.height,
                "background": page.background if page else project.background,
            },
            "elements": [
                {
                    "id": el.id,
                    "type": el.type.value if hasattr(el.type, "value") else str(el.type),
                    "name": el.name,
                    "x": el.x,
                    "y": el.y,
                    "width": el.width,
                    "height": el.height,
                    "rotation": el.rotation,
                    "opacity": el.opacity,
                    "z_index": el.z_index,
                    "text": el.text,
                    "src": el.src,
                }
                for el in (page.elements if page else [])
            ],
        }

        system_prompt = (
            "You are a canvas editor. Convert the user's instruction into a list of "
            "operations that modify the canvas. Use the provided element IDs. "
            "If an edit is ambiguous, do nothing for that part. "
            "Only include operations that are directly supported by the schema."
        )

        user_prompt = (
            f"Instruction: {instruction}\n\n"
            f"Canvas context (JSON):\n{json.dumps(context, indent=2)}"
        )

        try:
            plan = await llm.ask_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=CanvasEditPlan,
            )
        except Exception as exc:
            logger.warning("AI edit parsing failed: %s", exc)
            return None

        if not plan.operations:
            logger.info("AI edit produced no operations for project %s", project_id)
            return project

        applied = self._apply_edit_operations(project, plan.operations)
        if not applied:
            return project

        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project_id, project)

    def _apply_edit_operations(
        self,
        project: CanvasProject,
        operations: list[CanvasEditOperation],
    ) -> bool:
        if not project.pages:
            return False

        page = project.pages[0]
        settings = get_settings()
        applied = False

        def default_text_style(font_size: float | None = None) -> dict[str, Any]:
            return {
                "font_family": "Arial",
                "font_size": font_size or 16.0,
                "font_weight": "normal",
                "font_style": "normal",
                "text_align": "left",
                "vertical_align": "top",
                "line_height": 1.2,
                "letter_spacing": 0.0,
                "text_decoration": "none",
            }

        for op in operations:
            if isinstance(op, CanvasAddOperation):
                if len(page.elements) >= settings.canvas_max_elements:
                    logger.warning("Canvas element limit reached; skipping add operation.")
                    continue

                max_z = max((el.z_index for el in page.elements), default=0)
                fill = {"type": "solid", "color": op.fill_color} if op.fill_color else None
                text_style = None
                text_value = op.text

                if op.element_type == ElementType.TEXT:
                    if not text_value:
                        text_value = "New Text"
                    if not fill:
                        fill = {"type": "solid", "color": "#000000"}
                    text_style = default_text_style(op.font_size)

                points = None
                if op.element_type in (ElementType.LINE, ElementType.PATH):
                    points = [0.0, 0.0, op.width, op.height]

                element = CanvasElement(
                    id=str(uuid.uuid4()),
                    type=op.element_type,
                    name=op.name or f"{op.element_type.value.title()} {str(uuid.uuid4())[:4]}",
                    x=op.x,
                    y=op.y,
                    width=op.width,
                    height=op.height,
                    rotation=0.0,
                    scale_x=1.0,
                    scale_y=1.0,
                    opacity=op.opacity if op.opacity is not None else 1.0,
                    visible=True,
                    locked=False,
                    z_index=max_z + 1,
                    fill=fill,
                    corner_radius=op.corner_radius or 0.0,
                    text=text_value,
                    text_style=text_style,
                    src=op.src,
                    points=points,
                )
                page.elements.append(element)
                applied = True
                continue

            if isinstance(op, CanvasModifyOperation):
                target_index = next((i for i, el in enumerate(page.elements) if el.id == op.element_id), None)
                if target_index is None:
                    continue

                el = page.elements[target_index]
                updates: dict[str, Any] = {}
                if op.x is not None:
                    updates["x"] = op.x
                if op.y is not None:
                    updates["y"] = op.y
                if op.width is not None:
                    updates["width"] = op.width
                if op.height is not None:
                    updates["height"] = op.height
                if op.rotation is not None:
                    updates["rotation"] = op.rotation
                if op.opacity is not None:
                    updates["opacity"] = op.opacity
                if op.text is not None:
                    updates["text"] = op.text
                if op.fill_color is not None:
                    updates["fill"] = {"type": "solid", "color": op.fill_color}
                if op.font_size is not None:
                    existing_style = (el.text_style or {}).copy()
                    if not existing_style:
                        existing_style = default_text_style(op.font_size)
                    else:
                        existing_style["font_size"] = op.font_size
                    updates["text_style"] = existing_style

                if updates:
                    el_dict = el.model_dump()
                    el_dict.update(updates)
                    page.elements[target_index] = CanvasElement.model_validate(el_dict)
                    applied = True
                continue

            if isinstance(op, CanvasDeleteOperation):
                if not op.element_ids:
                    continue
                ids_set = set(op.element_ids)
                before = len(page.elements)
                page.elements = [el for el in page.elements if el.id not in ids_set]
                if len(page.elements) != before:
                    applied = True
                continue

            if isinstance(op, CanvasArrangeOperation):
                target = next((el for el in page.elements if el.id == op.element_id), None)
                if not target:
                    continue
                all_z = [el.z_index for el in page.elements]
                if not all_z:
                    continue
                target.z_index = max(all_z) + 1 if op.direction == "bring_to_front" else min(all_z) - 1
                applied = True

        return applied


# Global singleton
_canvas_service: CanvasService | None = None


def get_canvas_service() -> CanvasService:
    global _canvas_service
    if _canvas_service is None:
        _canvas_service = CanvasService()
    return _canvas_service
