#!/usr/bin/env python3
"""Initialize a new skill directory structure.

This script creates a new skill with the proper directory structure
and template files, making skill creation more efficient and reliable.

Usage:
    python init_skill.py <skill-name>

Example:
    python init_skill.py web-scraper
"""

import sys
from pathlib import Path

SKILL_MD_TEMPLATE = """---
name: {skill_name}
description: TODO - Describe what this skill does AND when to use it. Example: "Web scraping and data extraction. Use for: extracting data from websites, scraping product pages, collecting structured data."
---

# {skill_title}

## Overview
TODO - One sentence describing what this skill does.

## When to Use
TODO - List specific triggers/scenarios:
- Trigger scenario 1
- Trigger scenario 2

## Workflow
TODO - Define the step-by-step process:

### 1. Preparation
- **Objective**: [What this phase accomplishes]
- **Process**: [How to do it]

### 2. Execution
- **Objective**: [What this phase accomplishes]
- **Process**: [How to do it]

### 3. Verification
- **Objective**: [What this phase accomplishes]
- **Process**: [How to do it]

### 4. Delivery
- **Objective**: [What this phase accomplishes]
- **Process**: [How to do it]

## Guidelines
TODO - Add specific rules and constraints:
- Guideline 1
- Guideline 2
- Guideline 3

## Output Format
TODO - Define how results should be presented:

### Summary
[Brief overview of results]

### Detailed Results
[Structured output]

### Next Steps
[Recommendations if applicable]

## Example
TODO - Provide a concrete example:

**Input**: [Example user request]

**Output**: [Example response/result]
"""

SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Example script for {skill_name}.

TODO: Implement the script logic.

Usage:
    python {script_name} <args>
"""

import sys


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python {script_name} <args>")
        sys.exit(1)

    # TODO: Implement script logic
    print(f"Processing: {{sys.argv[1]}}")


if __name__ == "__main__":
    main()
'''

REFERENCE_TEMPLATE = """# {title}

TODO: Add reference documentation here.

## Overview
[Brief description of this reference]

## Details
[Detailed information]

## Examples
[Usage examples]
"""

TEMPLATE_TEMPLATE = """# {title} Template

TODO: Customize this template for your skill.

## Section 1
[Content placeholder]

## Section 2
[Content placeholder]
"""


def create_skill(skill_name: str, base_dir: str = ".") -> None:
    """Create a new skill directory structure.

    Args:
        skill_name: Name of the skill (e.g., "web-scraper")
        base_dir: Base directory for skill creation
    """
    # Normalize skill name
    skill_name = skill_name.lower().replace(" ", "-")
    skill_title = skill_name.replace("-", " ").title()

    # Create skill directory
    skill_dir = Path(base_dir) / skill_name
    if skill_dir.exists():
        sys.exit(1)

    # Create directories
    directories = [
        skill_dir,
        skill_dir / "scripts",
        skill_dir / "references",
        skill_dir / "templates",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md
    skill_md_path = skill_dir / "SKILL.md"
    skill_md_content = SKILL_MD_TEMPLATE.format(
        skill_name=skill_name,
        skill_title=skill_title,
    )
    skill_md_path.write_text(skill_md_content)

    # Create example script
    script_name = f"example_{skill_name.replace('-', '_')}.py"
    script_path = skill_dir / "scripts" / script_name
    script_content = SCRIPT_TEMPLATE.format(
        skill_name=skill_name,
        script_name=script_name,
    )
    script_path.write_text(script_content)

    # Create example reference
    reference_path = skill_dir / "references" / "guidelines.md"
    reference_content = REFERENCE_TEMPLATE.format(title=f"{skill_title} Guidelines")
    reference_path.write_text(reference_content)

    # Create example template
    template_path = skill_dir / "templates" / "output_template.md"
    template_content = TEMPLATE_TEMPLATE.format(title=skill_title)
    template_path.write_text(template_content)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        sys.exit(1)

    skill_name = sys.argv[1]
    base_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    create_skill(skill_name, base_dir)


if __name__ == "__main__":
    main()
