# Multi-Project Observability Requirements (v2)

**Date**: 2026-01-12
**Status**: APPROVED - Backend + Frontend Full Stack Plan
**Feature**: Multi-Project Support (Issue #6)

## 1. Overview

With the transition to a multi-project architecture (`SessionRegistry`, `GlobalLanguageServerPool`), the system state becomes more complex. Users and administrators need visibility into concurrent sessions, shared LSP resources, and isolation boundaries. This document defines the requirements for logging, backend API, and the frontend dashboard UI.

## 2. Structured Logging Requirements

The existing `MemoryLogHandler` captures formatted strings. To maintain compatibility while improving debuggability:

### LOG-1: Session Context Prefix
All logs generated within a session context MUST include the session ID and workspace name.
*   **Format**: `[Session: <short_id> | <project_name>] <message>`
*   **Example**: `[Session: a1b2 | backend-api] Tool dispatch: find_symbol`

### LOG-2: LSP Lifecycle Events
Critical LSP pool events must be logged at INFO level with resource details.
*   **Acquire**: `[LSP-Pool] Acquired python LSP for /abs/path/to/project (Session: a1b2)`
*   **Release**: `[LSP-Pool] Released python LSP for /abs/path/to/project (Ref Count: 0)`
*   **Reclaim**: `[LSP-Pool] Reclaiming idle python LSP (Idle: 3601s > 3600s)`
*   **Crash**: `[LSP-Pool] LSP Crashed: rust-analyzer (PID: 1234). Restarting...`

### LOG-3: Path Validation Failures
Security boundaries must be observable.
*   **Violation**: `[Security] Path Traversal Blocked: /etc/passwd escapes /abs/path/to/project (Session: a1b2)`

## 3. Dashboard API Requirements

The `SerenaDashboardAPI` (`src/serena/dashboard.py`) must be extended to expose the new architectural components.

### API-1: Active Sessions Endpoint
**Endpoint**: `GET /get_session_overview`
**Response Model**:
```json
{
  "active_sessions": [
    {
      "session_id": "uuid-string",
      "workspace_root": "/abs/path/to/project",
      "project_name": "project-name",
      "connected_at": "timestamp",
      "client_id": "optional-client-info",
      "acquired_lsps": ["python", "rust"]
    }
  ],
  "total_sessions": 2
}
```

### API-2: LSP Pool Statistics
**Endpoint**: `GET /get_lsp_pool_stats`
**Response Model**:
```json
{
  "active_lsps": [
    {
      "language": "python",
      "workspace_root": "/abs/path/to/project",
      "pid": 12345,
      "memory_mb": 150,  # Stretch goal
      "ref_count": 1,
      "active_sessions": ["uuid-string"],
      "status": "running"
    }
  ],
  "total_memory_usage_mb": 450
}
```

## 4. Frontend Requirements (UI/UX)

The frontend (`dashboard.js`, `index.html`) must be updated to visualize the new multi-project state.

### UI-1: Sessions View (New Section)
**Goal**: Visualize concurrent MCP clients.
*   **Location**: `page-overview` > New "Sessions" section (below "Executions").
*   **Visual**: Table or Card list.
*   **Data**:
    *   Session ID (shortened).
    *   Project Name.
    *   Connected Time.
    *   List of active LSPs (badges).
*   **Action**: "Terminate Session" button (calls `unbind_session`).

### UI-2: LSP Resource Monitor (New Page)
**Goal**: Monitor resource usage of the global pool.
*   **Location**: New Menu Item: "LSP Resources" (`page-lsp`).
*   **Visual**:
    *   **Summary Cards**: Total Active LSPs, Total Memory (est), Idle LSPs.
    *   **LSP Table**:
        *   Language (Icon/Text).
        *   Workspace Path.
        *   Status (Running/Idle/Reclaiming).
        *   Ref Count (Number of attached sessions).
        *   PID.
*   **Action**: "Restart LSP" button per row.

### UI-3: Config Overview Updates
*   **Update**: "Active Project" section is currently a singleton. Update it to show "Primary Session Project" or list all active projects if multiple exist.

## 5. Implementation Plan

### Phase 1: Backend API
1.  Add `get_session_overview()` method to `SessionRegistry`.
2.  Add `get_pool_stats()` method to `GlobalLanguageServerPool`.
3.  Implement Flask routes in `dashboard.py`.

### Phase 2: Frontend Logic (`dashboard.js`)
1.  Add `loadSessions()` and `loadLspStats()` polling functions.
2.  Implement `displaySessions(sessions)` renderer.
3.  Implement `displayLspStats(stats)` renderer.
4.  Add navigation logic for new "LSP Resources" page.

### Phase 3: Frontend Structure (`index.html`)
1.  Add HTML container for `<div id="active-sessions-display">`.
2.  Add HTML template for `<div id="page-lsp">`.
3.  Add Menu Item in `<div id="menu-dropdown">`.

### Phase 4: Styling (`dashboard.css`)
1.  Add styles for `session-card` and `lsp-table`.
2.  Ensure dark mode compatibility for new elements.