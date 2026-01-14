# Constitutional Fix Scope Insight

**Date**: 2026-01-13
**Context**: Perl LSP timeout fix via /constitutional-refactor

## Observation

When a commit contains only a few files, the full `/constitutional-fix` SHA-based workflow works efficiently:

1. **File-based audit** (what I did): Pass specific file paths to `/constitutional-audit`
   - Pros: Can audit before committing, flexible scope
   - Cons: Manual file selection, doesn't capture commit context

2. **SHA-based audit** (full ralph loop): Commit first, then `/constitutional-fix <SHA>`
   - Pros: Captures exact commit scope, audit sees committed state
   - Cons: Must commit first (even if violations exist)

## Key Insight

For small, focused commits (4-5 files like Perl LSP timeout fix):
- Either approach works
- SHA-based is cleaner for the ralph loop (commit → audit → fix → commit → re-audit)
- File-based is faster for quick one-off audits

## Recommendation

- **Small focused changes**: Use full `/constitutional-fix <SHA>` workflow
- **Large exploratory changes**: Use file-based audit to identify scope first
- **Single finding fixes**: Manual fix + commit + re-audit (token efficient)

## Evidence

Perl LSP timeout fix:
- 4 files changed (contract, impl, ls.py factory, tests)
- File-based audit found 1 finding → fixed → re-audit found 5 (stricter)
- Manual fix approach saved tokens vs full ralph loop for single finding
