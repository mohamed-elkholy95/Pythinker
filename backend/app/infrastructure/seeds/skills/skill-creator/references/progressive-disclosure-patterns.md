# Progressive Disclosure Patterns

## When to Split Content

Split content from SKILL.md to references/ when:
1. Documentation exceeds 100 lines
2. Content is variant-specific (different for different use cases)
3. Content is rarely needed (edge cases, troubleshooting)
4. Content is updateable separately (API schemas, configs)

## Pattern: Domain-Specific References

```
skill-name/
├── SKILL.md (core workflow, ~200 lines)
└── references/
    ├── domain_a.md (specifics for domain A)
    ├── domain_b.md (specifics for domain B)
    └── common_errors.md (troubleshooting)
```

In SKILL.md:
```markdown
## Domain-Specific Guidance

For detailed domain guidance, read the appropriate reference:
- Domain A tasks: `references/domain_a.md`
- Domain B tasks: `references/domain_b.md`
- Error troubleshooting: `references/common_errors.md`
```

## Pattern: Configuration-Driven

```
skill-name/
├── SKILL.md (workflow with config placeholders)
└── references/
    ├── config_dev.md (development settings)
    ├── config_prod.md (production settings)
    └── config_test.md (testing settings)
```

In SKILL.md:
```markdown
## Configuration

Load appropriate config based on environment:
- Development: `references/config_dev.md`
- Production: `references/config_prod.md`
- Testing: `references/config_test.md`
```

## Pattern: Script Library

```
skill-name/
├── SKILL.md (when to use each script)
└── scripts/
    ├── validate.py (input validation)
    ├── transform.py (data transformation)
    └── export.py (output generation)
```

In SKILL.md:
```markdown
## Available Scripts

Use these scripts for specific operations:

### validate.py
**When**: Before processing any input
**Usage**: `python scripts/validate.py <input_file>`

### transform.py
**When**: Converting between formats
**Usage**: `python scripts/transform.py <input> <output_format>`

### export.py
**When**: Generating final deliverables
**Usage**: `python scripts/export.py <data> <template>`
```

## Pattern: Template Library

```
skill-name/
├── SKILL.md (when to use each template)
└── templates/
    ├── report_formal.md
    ├── report_brief.md
    └── email_template.txt
```

In SKILL.md:
```markdown
## Templates

Select appropriate template based on context:

- **Formal report**: Use `templates/report_formal.md` for executive audiences
- **Brief summary**: Use `templates/report_brief.md` for quick updates
- **Email**: Use `templates/email_template.txt` for communication
```

## Pattern: API/Schema References

```
skill-name/
├── SKILL.md (core integration logic)
└── references/
    ├── api_endpoints.md (endpoint documentation)
    ├── data_schema.json (data structures)
    └── error_codes.md (error handling)
```

In SKILL.md:
```markdown
## API Integration

### Endpoints
For available endpoints, see `references/api_endpoints.md`

### Data Structures
Schema definitions in `references/data_schema.json`

### Error Handling
Error codes and recovery in `references/error_codes.md`
```

## Best Practices

1. **SKILL.md stays lean**: Max 500 lines, preferably under 300
2. **Clear navigation**: Tell users exactly when to read references
3. **No duplication**: Content lives in ONE place only
4. **Lazy loading**: References loaded only when needed
5. **Grep-friendly**: For large references, include search patterns

## Anti-Patterns to Avoid

1. **Everything in SKILL.md**: Bloated main file, slow loading
2. **Too many small references**: Navigation overhead
3. **Unclear triggers**: Users don't know when to read what
4. **Duplicate content**: Same info in multiple places
5. **Missing references**: Referenced files that don't exist
