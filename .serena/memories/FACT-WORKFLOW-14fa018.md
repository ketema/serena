# Fact: `validate_path()` must resolve symlinks BEFORE ...

**Category**: WORKFLOW
**Fact ID**: FACT-WORKFLOW-14fa018
**Created**: 2026-01-11T08:32:42Z
**Source Session**: 4fb5e8c8-5c2f-45e7-86e9-d08aea9bcdcb

## Fact Statement

`validate_path()` must resolve symlinks BEFORE boundary check to prevent traversal attacks. Add `.resolve()` call BEFORE `relative_to()` check.

## Keywords

`validate_path()`, resolve, symlinks, boundary, check, prevent, traversal, attacks, add, `resolve()`
