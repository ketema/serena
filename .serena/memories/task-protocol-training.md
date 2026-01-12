# TASK: Agent Coordination Protocol Upgrade Training

**Context**: Gemini (Orchestrator) has refined the tmux navigation protocol for history parsing. Claude (Agent) needs to learn these boundaries to improve its own `agent-coordination` skill execution.

**Protocol Upgrades**:
1.  **Prompt Boundary**: `❯` (U+276F) is the definitive user input start marker.
2.  **Ghost Text**: Grey text after `❯` (e.g. `↵ send`) is UI noise/suggestion, NOT user input. Ignore it.
3.  **Execution Blocks**: `⏺` (U+23FA) markers define atomic agent actions.
4.  **Completion Signal**: Return to `❯` (even with unsubmitted text) signals IDLE/WAITING state.

**Training Objective**:
1.  Read this file.
2.  Acknowledge the new markers.
3.  **PROVE Understanding**: Look at your own recent history (last 50 lines). Identify the exact timestamp/line where the last `RED PHASE COMPLETE` event occurred and the exact text of the User's pending prompt.

**Output**:
Write proof to `.serena/memories/task-protocol-training-response.md`.
