# CONTINUATION PROMPT: Multi-Project Path Resolution Bug

**Use this prompt to continue the investigation in a new Claude Code session.**

---

## Handoff Prompt

```
I need you to continue investigating a multi-project path resolution bug in the Serena MCP server. A previous session did extensive research but didn't find the root cause.

## The Bug (CRITICAL CONTEXT)

When multiple Claude Code instances connect to ONE shared HTTP MCP server, each working on DIFFERENT projects, path resolution uses the WRONG project's workspace.

**Concrete Evidence:**
- Session B activated OpenMemory at `/Users/ketema/projects/OpenMemory`
- Tool call error: `File not found: /Users/ketema/projects/serena/tools/backup_restore.py`
- Path was resolved against serena (HTTP server's CWD) instead of OpenMemory

**User's Key Insight:**
> "the http server root path is getting confused for the MCP root path"

The HTTP server runs from `/Users/ketema/projects/serena`. This path appears to leak into session workspaces.

## What Was Already Verified (DO NOT RE-INVESTIGATE)

1. SessionRegistry is a singleton shared correctly between agent and bridge
2. TaskExecutor uses copy_context() and context.run() correctly
3. self.project is a dynamic property (not cached)
4. bind_session creates new SessionContext objects
5. activate_session_project correctly unbinds/rebinds

## Investigation State File

Read this file FIRST:
```
.claude/multi-project-bug-investigation.md
```

It contains:
- Architecture summary
- Key file locations
- Code snippets already examined
- Hypotheses not yet ruled out
- Suggested next steps

## Your Task

1. Read the investigation state file
2. Pick up from "What To Do Next" section
3. Find the ROOT CAUSE (not just symptoms)
4. Report findings before proposing any fix

## Specific Hypotheses to Test

**Hypothesis 1: Default Workspace Leak**
`on_transport_session_created` uses `Path.cwd()` when workspace_root=None.
Maybe this default isn't being overwritten by activate_project?

**Hypothesis 2: ContextVar Timing**
Is the ContextVar set BEFORE copy_context() is called in issue_task?

**Hypothesis 3: Session Lookup Returns Stale Data**
Does get_session(session_id) return a session with the old workspace after activate_project updates it?

## Diagnostic Approach

Add logging to trace:
1. What workspace does on_transport_session_created set?
2. What workspace does activate_session_project set?
3. What does get_session() return when tool dispatch calls it?
4. What does get_current_session() return inside the thread?

## Key Files to Focus On

- src/serena/mcp_session_bridge.py (set_session_context, on_transport_session_created)
- src/serena/session_registry.py (get_session, bind_session)
- src/serena/agent.py (activate_session_project, get_active_project_or_raise)
- src/serena/mcp.py (tool dispatch, session bridge wiring)

## Constitutional Notes

- This is M2 DISCOVER CONTEXT phase
- DO NOT write implementation code yet
- Find root cause → report → get user approval → then M3 PLAN
```

---

## Prompt Engineering Analysis

### Techniques Applied

**1. Progressive Disclosure**
- Bug description first (most critical)
- Already-verified items to prevent redundant work
- Hypotheses ranked by likelihood
- Diagnostic steps as actionable sequence

**2. Authority + Commitment (Meincke)**
- "DO NOT RE-INVESTIGATE" - authority for verified items
- "Read this file FIRST" - commitment to sequence
- "Find ROOT CAUSE (not just symptoms)" - quality bar

**3. Scarcity (Meincke)**
- "Pick up from" - implies continuation, not restart
- "before proposing any fix" - gates premature action

**4. Méndez Reliability**
- Open-ended diagnostic approach (not yes/no)
- Encourages exploration of multiple hypotheses
- No punitive framing for uncertainty

**5. Hermeneutic Strict Constructionism**
- Concrete evidence quoted exactly
- User's key insight preserved verbatim
- No paraphrasing that could introduce drift

**6. Degrees of Freedom**
- Medium freedom: specific hypotheses provided but exploration allowed
- Clear structure without over-specification

### Anti-Patterns Avoided

- **Kitchen sink**: Focused context, not entire investigation history
- **Over-specification**: Hypotheses, not prescriptions
- **Correction loops**: Explicit "DO NOT RE-INVESTIGATE" prevents redundancy

---

## Quick Start for New Session

1. Open new Claude Code session in `/Users/ketema/projects/serena`
2. Paste the handoff prompt above
3. Agent will read `.claude/multi-project-bug-investigation.md`
4. Agent continues from diagnostic logging step

---

## If Stuck: Escalation Path

If the next agent can't find the root cause after diagnostic logging:

1. **Binary search in time**: Use git bisect to find when multi-project broke
2. **Minimal reproduction**: Create test that exercises the exact failure path
3. **External review**: Use AI Panel debug_assistance with full context

---

## Evidence Format for Findings

When root cause is found, document as:

```
ROOT CAUSE IDENTIFIED:
- Location: [file:line]
- Bug: [one sentence]
- Why it causes symptom: [explanation]
- Evidence: [diagnostic output showing the bug]
- Fix approach: [high-level, pending approval]
```
