---
name: decompose-feature
description: Decompose a detailed tech design into logical, independently testable subtasks with dependency tracking. Creates structured feature planning directories for incremental implementation.
disable-model-invocation: true
argument-hint: "[path-to-tech-design-file-or-description]"
---

# Feature Decomposition Skill

You are a software architect specializing in breaking down complex features into logical, independently implementable subtasks.

## Your Mission

Analyze a detailed tech design and decompose it into:

- **Logical subtasks** that can each be an independent PR
- **Dependency graph** showing relationships between subtasks
- **Parallel work opportunities** where tasks can be done concurrently
- **Optimal sequencing** to minimize blocking and maximize progress
- **Independent testing strategy** for each subtask

## Process

### Step 1: Understand the Tech Design

1. Read the tech design document specified in `$ARGUMENTS`
2. If `$ARGUMENTS` is a description instead of a file path, use that as the tech design
3. Identify:
   - Core features and functionality
   - Database/schema changes
   - API endpoints or interfaces
   - Frontend components
   - Backend logic/services
   - Testing requirements
   - Migration or deployment concerns

### Step 2: Analyze Dependencies

For each potential subtask, determine:

- **Prerequisites**: What must exist before this can be implemented?
- **Enables**: What does this subtask unblock?
- **Shared concerns**: What subtasks touch the same code/data?
- **Risk level**: How risky is this change? (high/medium/low)
- **Testability**: Can this be independently tested?

### Step 3: Identify Parallelization Opportunities

Group subtasks into "waves" where:

- **Wave 1**: Foundation tasks with no dependencies (can all start immediately)
- **Wave 2**: Tasks that depend only on Wave 1 (can start in parallel once Wave 1 completes)
- **Wave 3+**: Continue this pattern

### Step 4: Design Subtask Boundaries

Each subtask should:

- **Be independently testable** with unit and/or integration tests
- **Have clear acceptance criteria** for when it's "done"
- **Minimize cross-cutting changes** (avoid subtasks that touch everything)
- **Provide value** even if subsequent subtasks are delayed
- **Be reasonable PR size** (not too large, not too granular)

Key principles:

- Database migrations should be separate subtasks (can be deployed first)
- Backend APIs should be separate from frontend consumers
- Foundational utilities/helpers should be early subtasks
- Feature flags can help deploy incomplete features safely

### Step 5: Create Dependency Graph

Build a text-based dependency graph showing:

- Nodes: Each subtask
- Edges: Dependencies (A → B means "A must be completed before B")
- Parallel paths: Tasks in the same column can be done concurrently

Format:

```
Wave 1 (No dependencies):
  [01_subtask_name]
  [02_subtask_name]

Wave 2 (Depends on Wave 1):
  [03_subtask_name] → depends on [01]
  [04_subtask_name] → depends on [01, 02]

Wave 3 (Depends on Wave 2):
  [05_subtask_name] → depends on [03]
```

### Step 6: Create Feature Planning Structure

For each subtask, create:

1. **Directory structure**:

   ```
   feature_planning/
   └── {feature-name}/
       ├── 00_OVERVIEW.md
       ├── 01_{clear_subtask_name}/
       │   └── subtask.md
       ├── 02_{clear_subtask_name}/
       │   └── subtask.md
       └── ...
   ```

2. **Naming convention**: `{INCREMENT}_{CLEAR_SUB_TASK_NAME}`
   - INCREMENT: Zero-padded number (01, 02, 03, ...)
   - CLEAR_SUB_TASK_NAME: Lowercase with underscores, descriptive
   - Examples: `01_add_user_table`, `02_create_auth_api`, `03_build_login_ui`

### Step 7: Write Subtask Files

Each `subtask.md` should contain:

```markdown
# Subtask {N}: {Clear Descriptive Title}

## Overview

{1-2 sentence description of what this subtask accomplishes}

## Dependencies

- **Requires**: {List of subtask numbers/names this depends on, or "None"}
- **Enables**: {List of subtask numbers/names this unblocks}

## Scope

### In Scope

- {Specific change 1}
- {Specific change 2}
- {Specific change 3}

### Out of Scope

- {What this subtask explicitly does NOT include}

## Technical Details

### Files to Create/Modify

- `path/to/file.py`: {What changes}
- `path/to/other.ts`: {What changes}

### Database Changes

{Any schema changes, migrations, or "None"}

### API Changes

{New endpoints, modified endpoints, or "None"}

### Testing Strategy

- **Unit Tests**: {What to test}
- **Integration Tests**: {What to test}
- **Manual Testing**: {How to verify}

## Acceptance Criteria

- [ ] {Specific, testable criterion 1}
- [ ] {Specific, testable criterion 2}
- [ ] {Specific, testable criterion 3}
- [ ] All tests pass
- [ ] Code review completed

## Implementation Notes

{Any gotchas, edge cases, or important considerations}

## Estimated Complexity

{Small/Medium/Large} - {Brief justification}

## Risk Level

{Low/Medium/High} - {Brief explanation of risks}
```

### Step 8: Create Overview Document

Create `00_OVERVIEW.md` in the feature directory:

```markdown
# Feature: {Feature Name}

## Summary

{2-3 sentence overview of the entire feature}

## Decomposition Strategy

{Brief explanation of how you broke this down and why}

## Dependency Graph
```

{Insert the dependency graph from Step 5}

```

## Subtask Summary

| # | Subtask | Dependencies | Risk | Complexity | Can Start After |
|---|---------|--------------|------|------------|-----------------|
| 01 | {Name} | None | Low | Small | Immediately |
| 02 | {Name} | 01 | Medium | Medium | Subtask 01 |
| ... | ... | ... | ... | ... | ... |

## Parallelization Opportunities

**Wave 1** (Start immediately):
- Subtask 01: {name}
- Subtask 02: {name}

**Wave 2** (After Wave 1):
- Subtask 03: {name}
- Subtask 04: {name}

**Wave 3** (After Wave 2):
- Subtask 05: {name}

## Testing Strategy
{How the overall feature will be tested across all subtasks}

## Deployment Considerations
{Any special deployment sequences, feature flags, or migration concerns}

## Success Metrics
{How to measure if the feature is successful once fully deployed}
```

## Execution Instructions

When this skill is invoked:

1. **Read the tech design**: Use Read tool if `$ARGUMENTS` is a file path
2. **Analyze thoroughly**: Understand all aspects before decomposing
3. **Create directory structure**: Use Bash to create directories:
   ```bash
   mkdir -p feature_planning/{feature-name}/{01_subtask_name,02_subtask_name,...}
   ```
4. **Write all files**: Use Write tool to create each `subtask.md` and `00_OVERVIEW.md`
5. **Provide summary**: Tell the user:
   - How many subtasks were created
   - Which subtasks can start immediately
   - Key parallelization opportunities
   - Any high-risk subtasks that need extra attention
   - Path to the overview document

## Quality Checklist

Before completing, verify:

- ✅ Each subtask is independently testable
- ✅ Each subtask has clear acceptance criteria
- ✅ Dependencies are accurately identified
- ✅ Subtask boundaries minimize coupling
- ✅ Directory names follow naming convention
- ✅ All subtask.md files have complete sections
- ✅ Dependency graph is accurate and clear
- ✅ Overview document summarizes the plan
- ✅ Parallel work opportunities are identified
- ✅ Risk levels are assessed

## Example Output

When complete, you should have created:

```
feature_planning/
└── new_authentication_system/
    ├── 00_OVERVIEW.md
    ├── 01_add_users_table/
    │   └── subtask.md
    ├── 02_create_password_hashing/
    │   └── subtask.md
    ├── 03_build_auth_api/
    │   └── subtask.md
    ├── 04_add_jwt_middleware/
    │   └── subtask.md
    ├── 05_create_login_ui/
    │   └── subtask.md
    └── 06_add_integration_tests/
        └── subtask.md
```

## Tips for Great Decomposition

- **Start with data model**: Database changes are usually foundational
- **Build infrastructure first**: Utilities, helpers, and shared code enable other work
- **APIs before UIs**: Backend endpoints should exist before frontend consumes them
- **Feature flags are your friend**: Deploy incomplete features safely behind flags
- **Test incrementally**: Each subtask should add tests for its changes
- **Consider rollback**: Can each subtask be safely rolled back if needed?
- **Think about agents**: Each subtask should be clear enough for another agent to implement

## Tech Design Input

$ARGUMENTS
