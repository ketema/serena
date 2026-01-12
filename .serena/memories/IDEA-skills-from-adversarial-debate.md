# Skill Ideas from Adversarial Debate Session

**Date**: 2026-01-12
**Source**: Multi-Project Findings Debate (User vs Claude)
**Status**: IDEAS - Not yet implemented

## Proposed Skills

### 1. Potemkin Village Detection Skill

**Purpose**: Detect "integration theater" where unit tests pass but actual integration is broken.

**Complements**:
- Theater Test Detection (tests that pass when implementation is wrong)
- Mock Theater Detection (mocks that behave differently from real providers)

**Detection Criteria**:
- High unit test coverage with missing/failing integration tests
- Mocks pass, real components fail
- "Integration complete" claims without end-to-end verification
- Configuration bypassed in "integrated" code

**Trigger Phrases**:
- "Integration complete"
- "All tests passing"
- "Successfully connected X to Y"

**Verification Protocol**:
1. Identify integration claim
2. Find corresponding integration test (not unit test)
3. Run integration test against real stack
4. If no integration test exists → Potemkin Village risk

### 2. Adversarial Debate Skill

**Purpose**: Structured fact-based consensus building through challenge/rebuttal cycles.

**Protocol**:
1. Challenger presents numbered challenges with evidence
2. Defender provides rebuttals with counter-evidence
3. Iterate until consensus on each challenge
4. Record resolutions in persistent memory
5. Update affected documents based on consensus

**Key Principles**:
- "Challenge with facts, not opinions"
- "Concede when evidence is superior"
- "Mutual agreement when both partially correct"
- "Preserve debate record for future reference"

**Output Artifacts**:
- Debate record file (challenge/rebuttal/resolution)
- Updated documents reflecting consensus
- Score tracking (transparency on who "won" each point)

### 3. Multi-Agent Debate Integration

**Purpose**: Enable adversarial debate between Claude and other AI systems (Gemini, Codex) via agent-coordination skill.

**Architecture**:
```
Orchestrator (Claude)
├── Writes challenge to memory file
├── Sends prompt to Gemini pane via tmux
├── Waits for rebuttal in response file
├── Evaluates rebuttal
├── Records resolution
└── Iterates until consensus
```

**Benefits**:
- Different model perspectives catch different issues
- Like having "AI Panel on the system with you"
- Asynchronous debate survives compaction
- Memory-based handoff enables multi-day debates

**Integration Points**:
- `/agent-coordination` skill for tmux prompts
- Serena memories for debate state
- AI Panel for consensus validation

## Implementation Priority

1. **Potemkin Village Detection** - Highest (prevents false completion claims)
2. **Adversarial Debate** - Medium (valuable but manual process works)
3. **Multi-Agent Debate** - Lower (requires agent infrastructure)

## Reference

See `.serena/memories/adversarial-debate-multi-project-findings.md` for the debate that inspired these ideas.
