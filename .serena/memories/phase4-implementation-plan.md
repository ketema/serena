# Phase 4 Implementation Plan (Cleanup / Strangulation)

**Source**: Multi-Project Refactoring Roadmap v2.1 + Issue #6
**Goal**: Remove legacy single-session architecture after verified multi-session path.
**Branch**: feature/multi-project-support (all-or-nothing)

---

## 1) Contract Authority Validation (CL12-C)

- **Authoritative source**: `contracts/issue6_contract_index.py`
- **Required checklist**:
  - AUTHORITY declaration present
  - PRE/POST/INV/ERRORS with clause IDs
  - No PRE/ERRORS or INV/POST contradictions
- **Artifacts**:
  - Contract Authority Record (CAR)
  - Clause Registry

---

## 2) CL12 Traceability Standard (CL12-E)

- Every test docstring must cite exact clause IDs (PRE-N/POST-N/INV-N/ERROR-N/SEC-N)
- Every assertion message must cite the same clause IDs
- Maintain a traceability matrix: clause → test(s)

---

## 3) ContextVar Integration (merged into Cycle 1)

Checklist (enforced in Cycle 1 RED tests):
- ContextVar set/reset per request scope
- No cross-session leakage under concurrent runs
- No global fallback when context missing
- Explicit test for missing context path (should fail safely)

---

## 4) TDD Cycle 1 — SerenaAgent Statelessness (REQ-1)

**Contract**: `contracts/serena_agent_stateless_contract.py` (NEW)

**RED**:
- Tests proving no `_active_project` / `_current_session_id` in SerenaAgent
- All project resolution via `SessionRegistry` + `ContextVar`
- ContextVar checklist tests (from Section 3)

**GREEN**:
- Remove legacy state fields
- Resolve session/workspace dynamically via registry
- All methods use ContextVar for current session

---

## 5) TDD Cycle 2 — Project Config-Only (REQ-2)

**Contract**: `contracts/project_config_only_contract.py` (NEW)

**RED**:
- Tests proving Project owns no LSP lifecycle
- Project exposes only configuration (paths, ignore patterns, settings)

**GREEN**:
- Strip LSP lifecycle from Project class
- Ensure Project is pure configuration container

---

## 6) TDD Cycle 3 — LanguageServerManager Removal + LSP Consumer Migration (REQ-8)

**Existing Contracts**: 
- `contracts/global_lsp_pool_contract.py` (covers pool behavior)
- `contracts/lsp_capability_adapter_contract.py` (covers adapters)

**RED**:
- Tests validating SessionRegistry ↔ GlobalLanguageServerPool interaction
- Tests for all LSP consumer migration paths

**GREEN**:
- Remove `LanguageServerManager` class + all call sites
- Migrate all LSP consumers to GlobalLanguageServerPool APIs:
  - Acquire/release behavior
  - Workspace registration
  - Session isolation

---

## 7) TDD Cycle 4 — Integration Verification

**RED + GREEN**:
- Multi-session isolation
- Concurrent LSP requests
- Session create/teardown
- Cross-session error handling
- Pool cleanup
- ContextVar isolation
- Performance placeholders (relaxed thresholds: >1s warning, >5s failure)

---

## 8) Infrastructure (Existing - No Changes Needed)

| Component | Status | Contract |
|-----------|--------|----------|
| GlobalLanguageServerPool | ✅ Exists | ✅ global_lsp_pool_contract.py |
| SessionRegistry | ✅ Exists | ✅ session_registry_contract.py |
| LSPCapabilityAdapter | ✅ Exists | ✅ lsp_capability_adapter_contract.py |
| LSPTimeoutManager | ✅ Exists | ✅ lsp_timeout_contract.py |

---

## Contracts To Write (Before TDD Cycles)

1. **serena_agent_stateless_contract.py** - SerenaAgent without legacy state
2. **project_config_only_contract.py** - Project as config container only

---

**TDD Required**: RED → GREEN → COMMIT → REFACTOR (strict)
**Mock Policy**: No unverified mocks (CL10)
**Feature Branch**: All-or-nothing (git revert for rollback)
