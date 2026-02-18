"""Entry-point skill plugin loader.

Discovers and loads pip-installable skill plugins using Python's standard
``importlib.metadata.entry_points`` mechanism (PEP 517/660).

Third-party packages register themselves via their ``pyproject.toml``::

    [project.entry-points."pythinker.skills"]
    "my-plugin" = "my_package.skills:register"

The ``register`` callable receives no arguments and must return a
``SkillPlugin`` instance (or any object satisfying the protocol).

Integration (called from ``app/main.py`` lifespan startup, after MongoDB
and SkillRegistry are ready)::

    from app.infrastructure.plugins.skill_plugin_loader import load_skill_plugins

    plugin_count = await load_skill_plugins()

Design decisions:
- Plugins are loaded after the core seeding step so they can override or
  extend seeded skills.
- Failures in individual plugins are caught and logged; they never crash
  the application startup.
- Tools provided by plugins are registered with the DynamicToolsetManager's
  tool index so they participate in smart tool selection.
- Skills provided by plugins are persisted via SkillService (upsert) so
  they survive restarts and appear in the REST API.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.domain.models.skill import Skill
    from app.domain.services.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Entry-point group name that third-party plugins must register under
PLUGIN_ENTRY_POINT_GROUP = "pythinker.skills"


@runtime_checkable
class SkillPlugin(Protocol):
    """Protocol that all Pythinker skill plugins must satisfy.

    Third-party packages implement this interface and return an instance
    from their ``register()`` entry-point function.

    Example implementation::

        # my_package/skills.py
        from app.infrastructure.plugins.skill_plugin_loader import SkillPlugin


        class MyPlugin:
            def get_skills(self) -> list[Skill]:
                return [...]

            def get_tools(self) -> list[BaseTool]:
                return [...]


        def register() -> SkillPlugin:
            return MyPlugin()
    """

    def get_skills(self) -> list[Skill]:
        """Return skills this plugin contributes to Pythinker."""
        ...

    def get_tools(self) -> list[BaseTool]:
        """Return tools this plugin contributes to Pythinker."""
        ...


async def load_skill_plugins() -> int:
    """Discover and load all registered skill plugins.

    Iterates over all installed packages that declare an entry-point under
    the ``pythinker.skills`` group.  For each plugin:

    1. Imports and calls the ``register()`` callable.
    2. Upserts returned skills into MongoDB via ``SkillService``.
    3. Registers returned tools with ``DynamicToolsetManager``.
    4. Invalidates the ``SkillRegistry`` cache so new skills are visible.

    This function is idempotent — running it multiple times is safe because
    ``SkillService.upsert_skill()`` handles duplicates gracefully.

    Returns:
        Total number of plugins successfully loaded (not total skills/tools).
    """
    discovered = _discover_plugins()
    if not discovered:
        logger.debug(f"No plugins found under entry-point group '{PLUGIN_ENTRY_POINT_GROUP}'")
        return 0

    logger.info(
        f"Found {len(discovered)} plugin(s) under '{PLUGIN_ENTRY_POINT_GROUP}': " + ", ".join(discovered.keys())
    )

    loaded_count = 0
    for plugin_name, ep in discovered.items():
        try:
            plugin = _load_plugin(plugin_name, ep)
            if plugin is None:
                continue

            skills_count = await _register_plugin_skills(plugin_name, plugin)
            tools_count = await _register_plugin_tools(plugin_name, plugin)
            logger.info(f"Plugin '{plugin_name}' loaded: {skills_count} skill(s), {tools_count} tool(s)")
            loaded_count += 1

        except Exception as e:
            logger.exception(f"Failed to load plugin '{plugin_name}': {e}")

    if loaded_count > 0:
        # Refresh all skill caches so newly persisted plugin skills are visible
        # and SkillTriggerMatcher patterns are rebuilt alongside SkillRegistry.
        try:
            from app.domain.services.skill_registry import refresh_all_skill_caches

            await refresh_all_skill_caches()
            logger.debug("Skill caches refreshed after plugin load")
        except Exception as e:
            logger.warning(f"Could not refresh skill caches after plugin load: {e}")

    return loaded_count


def _discover_plugins() -> dict[str, object]:
    """Return all entry-points registered under ``pythinker.skills``.

    Uses ``importlib.metadata.entry_points`` (Python 3.12+ API — ``group``
    keyword argument is the stable cross-version interface).

    Returns:
        Dict mapping plugin name → EntryPoint object.
    """
    try:
        eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        return {ep.name: ep for ep in eps}
    except Exception as e:
        logger.warning(f"Entry-point discovery failed: {e}")
        return {}


def _load_plugin(name: str, ep: object) -> SkillPlugin | None:
    """Load a single plugin entry-point and return its SkillPlugin instance.

    Args:
        name: Plugin name (from entry-points key).
        ep: EntryPoint object from importlib.metadata.

    Returns:
        SkillPlugin instance, or None if loading/validation failed.
    """
    try:
        register_fn = ep.load()  # type: ignore[union-attr]
    except (ImportError, AttributeError) as e:
        logger.error(f"Plugin '{name}': failed to load entry-point: {e}")
        return None

    if not callable(register_fn):
        logger.error(f"Plugin '{name}': entry-point value is not callable (got {type(register_fn).__name__})")
        return None

    try:
        plugin = register_fn()
    except Exception as e:
        logger.error(f"Plugin '{name}': register() raised an exception: {e}")
        return None

    if not isinstance(plugin, SkillPlugin):
        # Soft check: log a warning but still try to use it if it has the methods
        has_get_skills = callable(getattr(plugin, "get_skills", None))
        has_get_tools = callable(getattr(plugin, "get_tools", None))
        if not (has_get_skills and has_get_tools):
            logger.error(
                f"Plugin '{name}': returned object does not implement SkillPlugin (missing get_skills and/or get_tools)"
            )
            return None
        logger.warning(
            f"Plugin '{name}': does not formally implement SkillPlugin protocol but has required methods — proceeding"
        )

    return plugin  # type: ignore[return-value]


async def _register_plugin_skills(plugin_name: str, plugin: SkillPlugin) -> int:
    """Upsert plugin-provided skills into MongoDB via SkillService.

    Args:
        plugin_name: Plugin name for log context.
        plugin: The loaded SkillPlugin instance.

    Returns:
        Number of skills successfully registered.
    """
    try:
        skills = plugin.get_skills()
    except Exception as e:
        logger.warning(f"Plugin '{plugin_name}': get_skills() raised: {e}")
        return 0

    if not skills:
        return 0

    count = 0
    try:
        from app.application.services.skill_service import get_skill_service

        skill_service = get_skill_service()
        for skill in skills:
            try:
                await skill_service.upsert_skill(skill)
                logger.debug(f"Plugin '{plugin_name}': upserted skill '{skill.id}'")
                count += 1
            except Exception as e:
                logger.warning(f"Plugin '{plugin_name}': failed to upsert skill '{skill.id}': {e}")
    except Exception as e:
        logger.warning(f"Plugin '{plugin_name}': SkillService unavailable: {e}")

    return count


async def _register_plugin_tools(plugin_name: str, plugin: SkillPlugin) -> int:
    """Register plugin-provided tools with DynamicToolsetManager.

    Converts each BaseTool's schemas into the dict format expected by
    ``DynamicToolsetManager.register_tools()``.

    Args:
        plugin_name: Plugin name for log context.
        plugin: The loaded SkillPlugin instance.

    Returns:
        Number of tools successfully registered.
    """
    try:
        tools = plugin.get_tools()
    except Exception as e:
        logger.warning(f"Plugin '{plugin_name}': get_tools() raised: {e}")
        return 0

    if not tools:
        return 0

    count = 0
    try:
        from app.domain.services.tools.dynamic_toolset import get_toolset_manager

        manager = get_toolset_manager()

        tool_schemas: list[dict] = []
        for tool in tools:
            try:
                # BaseTool.get_tools() returns list of tool dicts with "function" key
                schemas = tool.get_tools()
                tool_schemas.extend(schemas)
                count += 1
            except Exception as e:
                logger.warning(
                    f"Plugin '{plugin_name}': failed to get schemas from tool "
                    f"'{getattr(tool, 'name', type(tool).__name__)}': {e}"
                )

        if tool_schemas:
            manager.register_tools(tool_schemas)
            logger.debug(f"Plugin '{plugin_name}': registered {len(tool_schemas)} tool schema(s)")

    except Exception as e:
        logger.warning(f"Plugin '{plugin_name}': DynamicToolsetManager unavailable: {e}")

    return count


def list_installed_plugins() -> list[str]:
    """Return names of all currently installed Pythinker skill plugins.

    Useful for health checks and admin endpoints.

    Returns:
        List of plugin names (entry-point keys).
    """
    return list(_discover_plugins().keys())
