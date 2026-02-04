# Adversarial Coder + Tmux Offload Integration

**Purpose**: Document how adversarial-coder skill should use tmux-offload for test execution to preserve context and token efficiency.

## Current Problem

The adversarial-coder skill (Step 8: GREEN Phase Commit) says:
```
1. **Run tests** to verify GREEN (all passing)
```

But direct test execution (`uv run pytest`, `cargo test`) consumes 10-50K tokens and pollutes the forked context.

## Solution: Tmux Offload Integration

### Step 8 Modified Workflow

**Instead of:**
```bash
# ❌ Direct execution - wastes 10-50K tokens
cargo test -p mcp-server --features testing
uv run pytest tests/contracts/
```

**Do:**
```bash
# ✅ Offload to tmux pane - saves 95-99% tokens

# 1. Discover session and find/create idle pane
EXEC_SESSION=$(tmux list-sessions -F "#{session_name}" | head -1)
PANE=$(find_idle_pane "$EXEC_SESSION")
[ -z "$PANE" ] && PANE=$(create_exec_pane_if_needed "$EXEC_SESSION")

# 2. Offload test command (two-step pattern - MANDATORY)
tmux send-keys -t "$EXEC_SESSION:1.$PANE" "PYTHONPATH=. uv run pytest tests/contracts/test_mcp_session_isolation_contract.py -v"
tmux send-keys -t "$EXEC_SESSION:1.$PANE" C-m

# 3. Report to coordinator (DO NOT POLL)
echo "Tests running in pane $PANE. Notify me when complete."
```

### Result Retrieval (After Completion Signal)

**Coordinator signals**: "tests complete"

**Retrieve minimal output:**
```bash
# Summary only (preferred - 200-500 tokens)
tmux capture-pane -t "$EXEC_SESSION:1.$PANE" -p | grep -E "(passed|failed|error)" | tail -10

# If detail needed (5-20K tokens)
tmux capture-pane -t "$EXEC_SESSION:1.$PANE" -p | tail -50
```

### Token Economics

| Approach | Tokens | Context Impact |
|----------|--------|----------------|
| Direct pytest execution | 10-50K | HIGH - pollutes context |
| Offload + user report | 50-100 | MINIMAL |
| Offload + summary capture | 200-500 | LOW |
| Offload + full capture | 5-20K | MEDIUM (delayed) |

**Net Savings**: 95-99% token reduction

## Integration Points in adversarial-coder/skill.md

### Step 8: GREEN Phase Commit (Modified)

```markdown
## Step 8: GREEN Phase Commit

**After all error messages addressed:**

1. **Offload tests to tmux** (token-efficient verification):
   ```bash
   # Discover pane
   EXEC_SESSION=$(tmux list-sessions -F "#{session_name}" | head -1)
   PANE=$(find_idle_pane "$EXEC_SESSION" || create_exec_pane_if_needed "$EXEC_SESSION")
   
   # Offload (two-step pattern)
   tmux send-keys -t "$EXEC_SESSION:1.$PANE" "PYTHONPATH=. uv run pytest <test_file> -v"
   tmux send-keys -t "$EXEC_SESSION:1.$PANE" C-m
   
   # Report to coordinator
   echo "Tests running in pane $PANE. Notify when complete."
   ```

2. **Wait for coordinator signal** (DO NOT POLL)

3. **Retrieve summary on signal**:
   ```bash
   tmux capture-pane -t "$EXEC_SESSION:1.$PANE" -p | grep -E "(passed|failed)" | tail -5
   ```

4. **Verify traceability matrix** complete
5. **Verify side effect audit** clean
6. **Commit with WHY/EXPECTED format**
```

## Escalation Cases

**If no tmux session available:**
- Report to coordinator: "No tmux session found. Cannot offload tests."
- Coordinator decides: Create session OR fall back to direct execution (with context cost warning)

**If test execution times out (>10 min):**
- Report to coordinator with partial output
- Coordinator decides: Continue waiting OR investigate

## Constitutional Alignment

This integration preserves:
- **CL8 Efficiency**: Token savings prevent rework from context pollution
- **Adversarial Separation**: Coder still blind to test source (sees error messages, not test code)
- **Forked Context**: Test output stays in tmux pane, not coder's context

## Command Patterns by Language

| Language | Offload Command |
|----------|-----------------|
| Python | `PYTHONPATH=. uv run pytest <test_file> -v` |
| Rust | `cargo test -p <package> --features testing -- --nocapture` |
| Go | `go test -v ./...` |
| Haskell | `stack test` |
| JavaScript | `npm test` |

## Reference

- Tmux Offload Skill: `~/.claude/skills/tmux-offload/skill.md`
- Token efficiency data from skill documentation
- Two-step pattern is MANDATORY (single-line with C-m fails silently)
