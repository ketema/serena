# TODO: Refactor Haskell LSP Tests

**Date**: 2026-01-13
**Priority**: Medium
**Branch**: feature/multi-project-support

## Context

User contributed Haskell LSP support before developing constitutional skills.
All Haskell tests are currently failing.

## Failures Observed

```
FAILED test/solidlsp/haskell/test_haskell_basic.py::TestHaskellLanguageServer::test_data_type_constructor_references[haskell]
- SolidLSPException: No handler for: SMethod_TextDocumentReferences (-32601)
```

The Haskell Language Server (HLS) doesn't support `textDocument/references` method.

## Approach

Apply constitutional-refactor pattern (as exercised with Perl LSP):
1. Phase 1: Discovery - Build DISCONNECT MATRIX for HLS capabilities
2. Phase 2: Bridging (if needed)
3. Phase 3: Write CL12-compliant contract for HLS
4. Phase 4 RED: Write tests that respect HLS limitations
5. Phase 5 GREEN: Implement with proper XFAIL markers for unsupported features
6. Phase 6: Constitutional audit

## Similar Issues Found in Test Run

- **Erlang**: All 23 tests timing out (needs timeout configuration like Perl)
- **Zig**: Cross-file references failing (1 test)

## User Note

"I will give myself some grace" - pre-skills contribution, now opportunity to apply constitutional approach.
