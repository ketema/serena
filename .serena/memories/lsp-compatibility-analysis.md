# LSP Compatibility Analysis for Multi-Project Support

**Date**: 2026-01-12
**Status**: DRAFT - Findings from Adversarial Audit
**Author**: Gemini (Adversarial Mode)

## Executive Summary

The transition to multi-project support via `GlobalLanguageServerPool` relies on the assumption that LSPs fall into two clean categories:
1.  **Multi-Root**: Shareable instance (e.g., `rust-analyzer`, `pylsp`).
2.  **Single-Root**: Cheap, isolated instances per project (e.g., `tsserver` treated as single-root).

An audit of the 48 supported LSPs reveals that this binary categorization is insufficient. Three critical outliers break the resource management and isolation guarantees:

1.  **TypeScript (tsserver/vtsls)**: Resource intensive, stateful, and resistant to simple process isolation without explicit configuration.
2.  **Clangd**: Relies on global/project-local caches that may conflict if multiple instances run for related projects without unique cache path injection.
3.  **TerraformLS**: Claims multi-root capability but operates on directory-based module state, risking cross-project contamination if treated as a shared instance.

## Detailed Findings

### 1. TypeScript (`TypeScriptLanguageServer`) - The Resource Hog

**Contract**: `TsServerAdapterContract` (Single-Root / `multi_root_support=NONE`).
**Impact**: Spawns 1 process per project.
**Analysis**:
- `tsserver` is memory-heavy (often 300MB-1GB+ per instance).
- A user with 5 active TS projects (common in microservices) will spawn 5 heavy node processes.
- **Violation**: `CON-3: Memory Constraints`.
- **Technical Detail**: `tsserver` technically supports `workspaceFolders` but implementation details (`ProcessLaunchInfo` in `typescript_language_server.py`) hardcode `rootPath` and `rootUri`. It doesn't expose `tsserver`'s internal "project" abstraction effectively to the LSP client in a way that allows safe sharing.

### 2. Clangd (`ClangdLanguageServer`) - The Cache Corruptor

**Contract**: `ClangdAdapterContract` (Single-Root / `multi_root_support=NONE`).
**Impact**: Spawns 1 process per project.
**Analysis**:
- `clangd` relies on `.cache/clangd` or global caches.
- If multiple instances run for projects that share common headers/libraries (monorepo), they might race on cache writes.
- **Violation**: `REQ-1: Session Isolation`.
- **Missing Feature**: The current factory does not inject unique `--cache-path` arguments to isolate these instances.

### 3. Terraform (`TerraformLS`) - The False Friend

**Contract**: Detected as Multi-Root (`capabilities["workspace"]["workspaceFolders"] = True`).
**Impact**: Shared instance across all Terraform projects.
**Analysis**:
- Terraform state is directory-specific (`.terraform`).
- `terraform-ls` might handle `didChangeWorkspaceFolders`, but Terraform operations (init, plan) are strictly directory-bound.
- **Risk**: A shared instance might leak module state or confuse `terraform init` contexts between unrelated projects.
- **Recommendation**: Treat as Single-Root despite capabilities to ensure safety.

## Architectural Proposal: Capabilities-Driven Policy Injection

The binary "Multi/Single" distinction is too coarse. We need a **Policy-based** approach.

### New Concept: `LSPPoolingPolicy`

Instead of just `is_multi_root()`, the Adapter should return a Policy:

1.  **`SHARED_INSTANCE`** (Default for Multi-Root)
    - Stateless or capable of managing multiple roots safely.
    - Used for: Rust, Python, Go.

2.  **`ISOLATED_PROCESS`** (Default for Single-Root)
    - Separate process per root.
    - Used for: Generic single-root LSPs.

3.  **`ISOLATED_WITH_RESOURCE_MANAGEMENT`** (New)
    - Separate process, but managed carefully.
    - **TypeScript**: Needs memory limit flags (`--max-old-space-size`) injected.
    - **Clangd**: Needs `--cache-path` injection for isolation.

4.  **`FORCED_ISOLATION`** (New)
    - Claims multi-root but unsafe to share.
    - **Terraform**: Force separate process even if capability exists.

### Implementation Strategy

Refactor `LSPCapabilityAdapter` to include:
- `get_pooling_policy(language) -> PoolingPolicy`
- `get_launch_arguments(root) -> list[str]` (To inject cache paths/memory limits)

This moves the complexity of "how to run safely" into the Adapter, keeping `GlobalLanguageServerPool` generic.
