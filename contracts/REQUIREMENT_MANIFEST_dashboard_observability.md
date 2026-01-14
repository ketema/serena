# REQ-2026-002: Dashboard Multi-Project Observability Interface

## 1. Intent Traceability
- **Source Prose**:
  > "I can only describe what I expect as a human:
  > On the main dashboard I want to see a new card underneath Last Execution that shows observability stats on our multiproject serena instance:
  > - a list of active projects with their file paths
  > - a list of lsps that are instantiated and which projects are using them or used them last
  > - resource usage stats on each lsp (maybe the lsp resource usage has its on tab)
  > I want to see anything that would be relevant about serving multiple projects. all our contracts define expected behind the scenes behaviors, I want to SEE what is happening. the logs page should show all multi project observability messages."

- **Our Understanding**: Dashboard consumers (web UI, API clients) need to query multi-project observability data from SerenaAgent. This requires SerenaAgent to expose behavioral interfaces for session state and LSP pool state that are read-only, never raise exceptions, and return well-defined structures.

- **Ambiguity Score**: 2 (Ready for contracts)

## 2. The Actor Matrix
| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| Dashboard | Read-only queries | State mutation, LSP control |
| API Client | Read-only queries | State mutation, LSP control |
| SerenaAgent | Expose observability | Expose internal implementation details |

## 3. The State Transition
- **Initial State ($S_0$)**: SerenaAgent has private `_session_registry` and `_lsp_pool`; Dashboard cannot access
- **Transformation**: Define behavioral contract for observability interface
- **Terminal State ($S_1$)**: Dashboard can query session/LSP state via defined interface; internal state unchanged

## 4. Hard Invariants (The "Never" List)
| ID | Category | Invariant |
|----|----------|-----------|
| INV-OBS-01 | Read-Only | Observability queries MUST NOT mutate SerenaAgent state |
| INV-OBS-02 | Availability | Observability methods MUST NOT raise exceptions (always return valid structure) |
| INV-OBS-03 | Encapsulation | Observability interface MUST NOT expose internal implementation objects directly |
| INV-OBS-04 | Thread-Safety | Observability queries MUST be safe to call concurrently with mutations |

## 5. High-Entropy Zones (Adjudicated)
| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Property vs Method | Should observability be property or method? | Method (allows future params) | Default |
| Direct vs Copy | Return internal objects or copies? | Copies (INV-OBS-03) | Contract |
| Empty vs None | What if no sessions/LSPs? | Empty list, not None (INV-OBS-02) | Contract |
| Copy Semantics | Deep copy or shallow copy? | Shallow (new dicts, no internal objects exposed) | AI Panel |
| Thread Safety | How to ensure thread safety? | Delegate to SessionRegistry's lock (INV-4) | AI Panel |
| Exception Handling | How to suppress exceptions? | try/except returning empty structure | AI Panel |

## 5.1 AI Panel Recommendations (Incorporated)
| Recommendation | How Addressed |
|----------------|---------------|
| Specify copy semantics | Shallow copy - new dicts/lists, internal objects not returned |
| Thread safety mechanism | Delegate to SessionRegistry.get_session_overview() which uses lock |
| Adversarial test coverage | Test spec requires: concurrency, mutation attempts, exception scenarios |
| Backward compatibility | Tests verify exact response shape matches existing Dashboard expectations |

## 5.5 Rejected Alternatives
| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Behavioral interface | Expose `_session_registry` directly | Violates INV-OBS-03 (encapsulation) |
| Method returning dict | Property returning object | Methods allow future extension |
| Always return structure | Return None when empty | Simplifies consumer code, INV-OBS-02 |

## 6. Tool/API Interface Summary
| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| `get_session_overview()` | Return active session data | NO |
| `get_lsp_pool_stats()` | Return LSP pool statistics | NO |

## 6.5 Blocking Dependencies
| Unresolved Zone | Blocks |
|-----------------|--------|
| None | - |

## 7. Completion Promise (Ralph Loop Exit)
> "Dashboard observability endpoints (`/get_session_overview`, `/get_lsp_pool_stats`) return accurate real-time data, verified by:
> 1. `curl` against running Serena instance returns valid JSON (no 500 errors)
> 2. Response structure matches contract POST conditions exactly
> 3. With active project, session data reflects actual state
> 4. Constitutional audit shows ZERO VIOLATIONS"

## 8. Contract Authority
**Authoritative Source**: `contracts/serena_agent_observability_contract.py`

```
REQUIREMENT_MANIFEST_dashboard_observability.md (this file)
        ↓
contracts/serena_agent_observability_contract.py
        ↓
tests/test_serena_agent_observability_contract.py
        ↓
src/serena/agent.py (observability methods)
```

## 9. Revision History
| Date | Author | Change |
|------|--------|--------|
| 2026-01-14 | Claude + ketema | Initial manifest from req-elicit |
