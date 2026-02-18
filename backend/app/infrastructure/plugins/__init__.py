"""Plugin infrastructure for Pythinker.

Provides entry-point based plugin discovery so third-party pip packages
can contribute skills and tools without modifying the core codebase.

Plugin registration (in a third-party package's pyproject.toml)::

    [project.entry-points."pythinker.skills"]
    "my-plugin-name" = "my_package.skills:register"

The ``register`` callable must return a ``SkillPlugin`` instance.
"""
