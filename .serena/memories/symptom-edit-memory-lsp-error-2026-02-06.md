# Symptom: edit_memory fails with LSP error

**Date**: 2026-02-06
**Branch**: ketema
**Related to**: Server-centric LSP architecture rethink (handoff-m1-lsp-architecture-rethink-2026-02-06)

## Error
```
mcp__serena__edit_memory → Error: 'LanguageServerCodeEditor' object has no attribute 'get_active_project'
```

## Context
- Called `edit_memory` on `handoff-m1-lsp-architecture-rethink-2026-02-06`
- Serena project was activated (`activate_project("serena")` succeeded earlier)
- Other Serena tools (read_memory, write_memory, list_memories) worked fine
- `edit_memory` uses `LanguageServerCodeEditor` internally, which requires active project context

## Likely Cause
`edit_memory` routes through the code editor which depends on `get_active_project()` — but memory files aren't code files. The editor may be attempting LSP-based editing on a markdown memory file, hitting the session/project context gap that's the subject of the architecture rethink.

## Workaround
Use `write_memory` (full rewrite) instead of `edit_memory` (incremental edit) when this occurs.

## Relevance
Another symptom of the authority mismatch: the tool dispatch assumes LSP context is always available, but in HTTP multi-session mode, the context binding may not be in the expected state.
