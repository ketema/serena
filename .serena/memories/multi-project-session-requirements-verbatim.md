# Multi-Project Session Isolation Requirements (Verbatim)

**Date**: 2026-01-11
**Branch**: feature/multi-project-support
**AI Panel Conversation**: e9c3ec5e-6d3a-438b-9469-6f07eb5b4dcf

## Purpose

This document captures requirements VERBATIM for plan adherence checking.
Contracts and implementations MUST satisfy these requirements.

---

## Requirements

### REQ-1: Session Isolation
Multiple MCP clients can connect simultaneously with session isolation.

### REQ-2: LSP Resource Sharing (Revised)
LSP instances are shared across sessions **where possible and correct**.
Multi-root LSPs share a single instance across compatible sessions.
Single-root LSPs require per-root instances.

### REQ-3: Path Validation
Session A cannot access files in Session B's workspace (PathValidation).

### REQ-4: Polymorphic LSP Handling
Different LSPs have different multi-root capabilities - handle polymorphically via adapters.

### REQ-5: Idle Reclamation
LSPs reclaimed after idle timeout when no sessions using them.

---

## Constraints

### CON-1: LSP Isolation Responsibility
LSPs don't know about sessions - Serena must handle all isolation.

### CON-2: Single-Root LSP Limitation
Some LSPs (tsserver, clangd) are single-root only - cannot dynamically add workspace folders.

### CON-3: Memory Constraints
rust-analyzer can use 500MB-1.5GB. Resource conservation critical.

### CON-4: Transport Support
Must support three MCP transports: stdio (process lifetime), SSE (connection lifetime), streaming HTTP (header-based).

### CON-5: Sync Architecture
Threading.Lock and daemon threads - no asyncio.

---

## Design Decisions (From AI Panel Review)

### DD-1: Connection Pooler Pattern
APPROVED. LSP management follows database connection pooler pattern.

### DD-2: Pool Key Strategy
- Multi-root LSPs: Key by `language`
- Single-root LSPs: Key by `(language, rootUri)`

### DD-3: Lock Hierarchy
`session_lock → pool_lock` (always acquire in this order)

### DD-4: Reference Counting + Idle Timeout (Hybrid)
- Track session references per LSP
- When ref_count == 0: Start idle timer
- When idle_time > timeout: Reclaim LSP

### DD-5: Workspace Folder Cleanup
- Multi-root LSPs: Send `workspace/didChangeWorkspaceFolders(removed=[...])` on session disconnect
- Single-root LSPs: Terminate instance if last session disconnects

### DD-6: Capability Detection Sequence
1. Start LSP
2. Send initialize request
3. Parse ServerCapabilities
4. Cache for adapter routing
5. Only then allow session workspace registration

### DD-7: Crash Recovery
Reuse existing `_ensure_functional_ls()` pattern - checks `is_running()`, auto-restarts if crashed.

---

## User Clarifications (From Review)

### UC-1: Multi-Root State Corruption
USER RESPONSIBILITY. Projects with interdependencies would exhibit this behavior with or without Serena. Users should organize their projects correctly.
ACTION: Note the risk. Perform PoC after implementation.

### UC-2: Response Filtering
NOT A SERENA CONCERN. LSP returns symbols; Serena manages session scope. Agent config handles scope violations, not Serena.

---

## Components Required

1. **GlobalLanguageServerPool** - Manages LSPs as shared global resources
2. **LSPCapabilityAdapter** - Polymorphic interface for LSP differences
3. **Session-Aware Tool Dispatch** - PathValidation + routing through pool

---

## Contract Files (To Be Created)

- `contracts/global_lsp_pool_contract.py`
- `contracts/lsp_capability_adapter_contract.py`
- `contracts/session_tool_dispatch_contract.py`

---

## Traceability

| Requirement | Component | Contract |
|-------------|-----------|----------|
| REQ-1 | SessionRegistry | session_registry_contract.py (exists) |
| REQ-2 | GlobalLanguageServerPool | global_lsp_pool_contract.py |
| REQ-3 | PathValidation | path_validation_contract.py (exists) |
| REQ-4 | LSPCapabilityAdapter | lsp_capability_adapter_contract.py |
| REQ-5 | LSPTimeoutManager + Pool | lsp_timeout_contract.py (exists) + pool |
