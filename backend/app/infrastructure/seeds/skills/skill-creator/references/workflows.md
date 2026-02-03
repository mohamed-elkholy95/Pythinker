# Workflow Design Patterns

## Sequential Workflow

Best for: Linear processes with clear dependencies

```markdown
## Workflow
1. **Initialize**
   - Set up environment
   - Validate inputs

2. **Execute**
   - Perform main operation
   - Handle edge cases

3. **Verify**
   - Check outputs
   - Validate against requirements

4. **Deliver**
   - Format results
   - Notify user
```

## Conditional Workflow

Best for: Tasks with branching logic

```markdown
## Workflow

### Analysis Phase
Determine task type based on:
- Input format
- User requirements
- Available resources

### Execution Phase
**If simple task:**
1. Quick processing
2. Direct output

**If complex task:**
1. Break into subtasks
2. Process sequentially
3. Aggregate results

**If error encountered:**
1. Log error details
2. Attempt recovery
3. Report to user if unrecoverable
```

## Iterative Workflow

Best for: Tasks requiring refinement

```markdown
## Workflow
1. **Draft**: Create initial version
2. **Review**: Check against requirements
3. **Refine**: Address gaps (max 3 iterations)
4. **Finalize**: Produce final output
```

## Parallel Workflow

Best for: Independent subtasks

```markdown
## Workflow
Execute in parallel:
- [ ] Task A: [description]
- [ ] Task B: [description]
- [ ] Task C: [description]

Then aggregate results into final output.
```

## Research Workflow

Best for: Information gathering tasks

```markdown
## Workflow
1. **Search**: Find relevant sources using info_search_web
2. **Filter**: Identify most authoritative sources
3. **Extract**: Use browser_get_content for detailed reading
4. **Verify**: Cross-reference across multiple sources
5. **Synthesize**: Compile findings with citations
```

## Code Review Workflow

Best for: Code analysis tasks

```markdown
## Workflow
1. **Read**: Load target file(s) completely
2. **Analyze**: Identify issues by category
   - Security vulnerabilities
   - Performance concerns
   - Code quality issues
3. **Classify**: Rank by severity (CRITICAL/HIGH/MEDIUM/LOW)
4. **Report**: Format findings with line numbers and fixes
```

## Data Processing Workflow

Best for: ETL and data transformation tasks

```markdown
## Workflow
1. **Load**: Read input data
2. **Validate**: Check data integrity
3. **Transform**: Apply processing logic
4. **Quality Check**: Verify output
5. **Export**: Write to target format
```
