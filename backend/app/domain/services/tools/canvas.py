"""Canvas tool for agent-driven visual design creation."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.domain.models.canvas import CanvasElement, ElementType

if TYPE_CHECKING:
    from app.application.services.canvas_service import CanvasService
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class CanvasTool(BaseTool):
    """Tool for creating and manipulating canvas projects.

    Enables the agent to create visual designs (posters, diagrams, social graphics)
    by programmatically creating canvas projects and adding/modifying elements.
    """

    name: str = "canvas"

    def __init__(
        self,
        canvas_service: CanvasService,
        user_id: str,
        session_id: str,
    ) -> None:
        super().__init__()
        self._canvas_service = canvas_service
        self._user_id = user_id
        self._session_id = session_id
        self._active_project_id: str | None = None

    @tool(
        name="canvas_create_project",
        description="Create a new canvas project for visual design. Returns the project ID.",
        parameters={
            "name": {
                "type": "string",
                "description": "Project name (e.g. 'Marketing Poster', 'Social Media Banner')",
            },
            "width": {
                "type": "number",
                "description": "Canvas width in pixels (default 1920)",
            },
            "height": {
                "type": "number",
                "description": "Canvas height in pixels (default 1080)",
            },
            "background": {
                "type": "string",
                "description": "Background color hex code (default '#FFFFFF')",
            },
        },
        required=["name"],
    )
    async def canvas_create_project(
        self,
        name: str,
        width: float = 1920.0,
        height: float = 1080.0,
        background: str = "#FFFFFF",
    ) -> ToolResult:
        project = await self._canvas_service.create_project(
            user_id=self._user_id,
            name=name,
            width=width,
            height=height,
            background=background,
            session_id=self._session_id,
        )
        self._active_project_id = project.id
        return ToolResult(
            success=True,
            data={"project_id": project.id, "name": project.name},
            message=f"Created canvas project '{name}' ({int(width)}x{int(height)}). Project ID: {project.id}",
        )

    @tool(
        name="canvas_get_state",
        description="Get the current state of the active canvas project.",
        parameters={
            "project_id": {
                "type": "string",
                "description": "Project ID (uses active project if not specified)",
            },
        },
        required=[],
    )
    async def canvas_get_state(
        self,
        project_id: str | None = None,
    ) -> ToolResult:
        pid = project_id or self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project. Create one first.", data=None)

        project = await self._canvas_service.get_project(pid)
        if not project:
            return ToolResult(success=False, message=f"Project {pid} not found.", data=None)

        elements: list[dict[str, Any]] = []
        for page in project.pages:
            for el in page.elements:
                elements.append(
                    {
                        "id": el.id,
                        "type": el.type.value if hasattr(el.type, "value") else str(el.type),
                        "name": el.name,
                        "x": el.x,
                        "y": el.y,
                        "width": el.width,
                        "height": el.height,
                    }
                )

        return ToolResult(
            success=True,
            data={
                "project_id": project.id,
                "name": project.name,
                "width": project.width,
                "height": project.height,
                "pages": len(project.pages),
                "elements": elements,
            },
            message=f"Canvas '{project.name}': {len(elements)} elements across {len(project.pages)} page(s).",
        )

    @tool(
        name="canvas_add_element",
        description="Add a shape, text, or image element to the canvas.",
        parameters={
            "element_type": {
                "type": "string",
                "enum": ["rectangle", "ellipse", "text", "image", "line"],
                "description": "Type of element to add",
            },
            "x": {"type": "number", "description": "X position in pixels"},
            "y": {"type": "number", "description": "Y position in pixels"},
            "width": {"type": "number", "description": "Width in pixels"},
            "height": {"type": "number", "description": "Height in pixels"},
            "fill_color": {
                "type": "string",
                "description": "Fill color hex code (e.g. '#FF5733')",
            },
            "text": {
                "type": "string",
                "description": "Text content (for text elements)",
            },
            "font_size": {
                "type": "number",
                "description": "Font size (for text elements, default 24)",
            },
            "src": {
                "type": "string",
                "description": "Image URL (for image elements)",
            },
            "opacity": {
                "type": "number",
                "description": "Opacity 0-1 (default 1)",
            },
            "corner_radius": {
                "type": "number",
                "description": "Corner radius for rounded rectangles",
            },
            "name": {
                "type": "string",
                "description": "Element name/label",
            },
        },
        required=["element_type", "x", "y", "width", "height"],
    )
    async def canvas_add_element(
        self,
        element_type: str,
        x: float,
        y: float,
        width: float,
        height: float,
        fill_color: str | None = None,
        text: str | None = None,
        font_size: float = 24.0,
        src: str | None = None,
        opacity: float = 1.0,
        corner_radius: float = 0.0,
        name: str = "",
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project. Create one first.", data=None)

        el_type = ElementType(element_type)
        fill = {"type": "solid", "color": fill_color} if fill_color else None
        text_style = None
        if el_type == ElementType.TEXT:
            text_style = {
                "font_family": "Arial",
                "font_size": font_size,
                "font_weight": "normal",
                "font_style": "normal",
                "text_align": "left",
                "vertical_align": "top",
                "line_height": 1.2,
                "letter_spacing": 0.0,
                "text_decoration": "none",
            }
            if not fill:
                fill = {"type": "solid", "color": "#000000"}

        element = CanvasElement(
            id=str(uuid.uuid4()),
            type=el_type,
            name=name or f"{element_type.title()} {str(uuid.uuid4())[:4]}",
            x=x,
            y=y,
            width=width,
            height=height,
            opacity=opacity,
            corner_radius=corner_radius,
            fill=fill,
            text=text,
            text_style=text_style,
            src=src,
        )

        result = await self._canvas_service.add_element(pid, element)
        if not result:
            return ToolResult(success=False, message="Failed to add element.", data=None)

        return ToolResult(
            success=True,
            data={"project_id": pid, "element_id": element.id, "type": element_type},
            message=f"Added {element_type} element '{element.name}' at ({int(x)}, {int(y)}), size {int(width)}x{int(height)}.",
        )

    @tool(
        name="canvas_modify_element",
        description="Modify properties of an existing canvas element.",
        parameters={
            "element_id": {"type": "string", "description": "ID of the element to modify"},
            "x": {"type": "number", "description": "New X position"},
            "y": {"type": "number", "description": "New Y position"},
            "width": {"type": "number", "description": "New width"},
            "height": {"type": "number", "description": "New height"},
            "fill_color": {"type": "string", "description": "New fill color"},
            "opacity": {"type": "number", "description": "New opacity 0-1"},
            "text": {"type": "string", "description": "New text content"},
            "font_size": {"type": "number", "description": "New font size"},
            "rotation": {"type": "number", "description": "Rotation in degrees"},
        },
        required=["element_id"],
    )
    async def canvas_modify_element(
        self,
        element_id: str,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        fill_color: str | None = None,
        opacity: float | None = None,
        text: str | None = None,
        font_size: float | None = None,
        rotation: float | None = None,
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project.", data=None)

        updates: dict[str, Any] = {}
        if x is not None:
            updates["x"] = x
        if y is not None:
            updates["y"] = y
        if width is not None:
            updates["width"] = width
        if height is not None:
            updates["height"] = height
        if opacity is not None:
            updates["opacity"] = opacity
        if text is not None:
            updates["text"] = text
        if rotation is not None:
            updates["rotation"] = rotation
        if fill_color is not None:
            updates["fill"] = {"type": "solid", "color": fill_color}
        if font_size is not None:
            updates["text_style"] = {
                "font_family": "Arial",
                "font_size": font_size,
                "font_weight": "normal",
                "font_style": "normal",
                "text_align": "left",
                "vertical_align": "top",
                "line_height": 1.2,
                "letter_spacing": 0.0,
                "text_decoration": "none",
            }

        if not updates:
            return ToolResult(success=False, message="No updates specified.", data=None)

        result = await self._canvas_service.modify_element(pid, element_id, updates)
        if not result:
            return ToolResult(success=False, message=f"Element {element_id} not found.", data=None)

        return ToolResult(
            success=True,
            data={"project_id": pid, "element_id": element_id, "updated_fields": list(updates.keys())},
            message=f"Modified element {element_id}: updated {', '.join(updates.keys())}.",
        )

    @tool(
        name="canvas_delete_elements",
        description="Delete one or more elements from the canvas.",
        parameters={
            "element_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of element IDs to delete",
            },
        },
        required=["element_ids"],
    )
    async def canvas_delete_elements(
        self,
        element_ids: list[str],
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project.", data=None)

        result = await self._canvas_service.delete_elements(pid, element_ids)
        if not result:
            return ToolResult(success=False, message="Failed to delete elements.", data=None)

        return ToolResult(
            success=True,
            data={"project_id": pid, "deleted": len(element_ids)},
            message=f"Deleted {len(element_ids)} element(s).",
        )

    @tool(
        name="canvas_generate_image",
        description="Generate an AI image and add it to the canvas.",
        parameters={
            "prompt": {
                "type": "string",
                "description": "Image generation prompt (detailed description of desired image)",
            },
            "x": {"type": "number", "description": "X position on canvas (default 0)"},
            "y": {"type": "number", "description": "Y position on canvas (default 0)"},
            "width": {"type": "number", "description": "Image width (default 512)"},
            "height": {"type": "number", "description": "Image height (default 512)"},
        },
        required=["prompt"],
    )
    async def canvas_generate_image(
        self,
        prompt: str,
        x: float = 0.0,
        y: float = 0.0,
        width: float = 512.0,
        height: float = 512.0,
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project.", data=None)

        try:
            urls = await self._canvas_service.generate_image(prompt, int(width), int(height))
        except ValueError as e:
            return ToolResult(success=False, message=str(e), data=None)

        if not urls:
            return ToolResult(success=False, message="Image generation returned no results.", data=None)

        # Add the generated image as an element
        image_url = urls[0]
        element = CanvasElement(
            id=str(uuid.uuid4()),
            type=ElementType.IMAGE,
            name=f"AI Image: {prompt[:30]}",
            x=x,
            y=y,
            width=width,
            height=height,
            src=image_url,
        )
        await self._canvas_service.add_element(pid, element)

        return ToolResult(
            success=True,
            data={"project_id": pid, "element_id": element.id, "image_url": image_url},
            message=f"Generated image from prompt '{prompt[:50]}...' and added to canvas at ({int(x)}, {int(y)}).",
        )

    @tool(
        name="canvas_arrange_layer",
        description="Change element z-order (layering).",
        parameters={
            "element_id": {"type": "string", "description": "Element ID"},
            "action": {
                "type": "string",
                "enum": ["bring_to_front", "send_to_back"],
                "description": "Layer action",
            },
        },
        required=["element_id", "action"],
    )
    async def canvas_arrange_layer(
        self,
        element_id: str,
        action: str,
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project.", data=None)

        project = await self._canvas_service.get_project(pid)
        if not project:
            return ToolResult(success=False, message="Project not found.", data=None)

        # Find max/min z_index
        all_z = [el.z_index for page in project.pages for el in page.elements]
        if not all_z:
            return ToolResult(success=False, message="No elements to arrange.", data=None)

        new_z = max(all_z) + 1 if action == "bring_to_front" else min(all_z) - 1

        result = await self._canvas_service.modify_element(pid, element_id, {"z_index": new_z})
        if not result:
            return ToolResult(success=False, message=f"Element {element_id} not found.", data=None)

        return ToolResult(
            success=True,
            data={"project_id": pid, "element_id": element_id, "z_index": new_z},
            message=f"Element {element_id} moved to {'front' if action == 'bring_to_front' else 'back'}.",
        )

    @tool(
        name="canvas_export",
        description="Export the canvas project as a downloadable file.",
        parameters={
            "format": {
                "type": "string",
                "enum": ["png", "json"],
                "description": "Export format (default 'json')",
            },
        },
        required=[],
    )
    async def canvas_export(
        self,
        format: str = "json",
    ) -> ToolResult:
        pid = self._active_project_id
        if not pid:
            return ToolResult(success=False, message="No active canvas project.", data=None)

        project = await self._canvas_service.get_project(pid)
        if not project:
            return ToolResult(success=False, message="Project not found.", data=None)

        if format == "json":
            return ToolResult(
                success=True,
                data=project.model_dump(),
                message=f"Exported canvas '{project.name}' as JSON.",
            )

        return ToolResult(
            success=True,
            data={"project_id": pid, "format": format},
            message=f"Export as {format} is available in the canvas editor. Open /canvas/{pid} to download.",
        )
