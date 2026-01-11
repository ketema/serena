# CLAUDE CODE EXTENSIONS TO MCP-BASED CONSTITUTION

**Precedence**: Constitutional principles (CL1-CL8, QS1-QS6, M1-M5) are foundational
**Base Constitution**: All constitutional laws, quality standards, macros, and enforcement levels apply
If any instruction in this document conflicts with the constitutional system prompt currently in effect (CL*, QS*, M1–M5), the constitutional system prompt ALWAYS overrides.
**Additions**: Claude Code-specific internal tools and behaviors that integrate with the constitutional framework

---

## Serena Project-Specific Commands

**Essential Commands (use these exact commands):**
- `uv run poe format` - Format code (BLACK + RUFF) - ONLY allowed formatting command
- `uv run poe type-check` - Run mypy type checking - ONLY allowed type checking command
- `uv run poe test` - Run tests with default markers (excludes java/rust by default)
- `uv run poe test -m "python or go"` - Run specific language tests
- `uv run poe test -m vue` - Run Vue tests
- `uv run poe lint` - Check code style without fixing

**Test Markers:**
Available pytest markers for selective testing:
- `python`, `go`, `java`, `rust`, `typescript`, `vue`, `php`, `perl`, `powershell`, `csharp`, `elixir`, `terraform`, `clojure`, `swift`, `bash`, `ruby`, `ruby_solargraph`
- `snapshot` - for symbolic editing operation tests

**Project Management:**
- `uv run serena-mcp-server` - Start MCP server from project root
- `uv run index-project` - Index project for faster tool performance

**Always run format, type-check, and test before completing any task.**

---

## Serena Architecture Overview

Serena is a dual-layer coding agent toolkit:

### Core Components

**1. SerenaAgent (`src/serena/agent.py`)**
- Central orchestrator managing projects, tools, and user interactions
- Coordinates language servers, memory persistence, and MCP server interface
- Manages tool registry and context/mode configurations

**2. SolidLanguageServer (`src/solidlsp/ls.py`)**
- Unified wrapper around Language Server Protocol (LSP) implementations
- Provides language-agnostic interface for symbol operations
- Handles caching, error recovery, and multiple language server lifecycle

**3. Tool System (`src/serena/tools/`)**
- **file_tools.py** - File system operations, search, regex replacements
- **symbol_tools.py** - Language-aware symbol finding, navigation, editing
- **memory_tools.py** - Project knowledge persistence and retrieval
- **config_tools.py** - Project activation, mode switching
- **workflow_tools.py** - Onboarding and meta-operations

**4. Configuration System (`src/serena/config/`)**
- **Contexts** - Define tool sets for different environments (desktop-app, agent, ide-assistant)
- **Modes** - Operational patterns (planning, editing, interactive, one-shot)
- **Projects** - Per-project settings and language server configs

### Language Support Architecture

Each supported language has:
1. **Language Server Implementation** in `src/solidlsp/language_servers/`
2. **Runtime Dependencies** - Automatic language server downloads when needed
3. **Test Repository** in `test/resources/repos/<language>/`
4. **Test Suite** in `test/solidlsp/<language>/`

### Memory & Knowledge System

- **Markdown-based storage** in `.serena/memories/` directories
- **Project-specific knowledge** persistence across sessions
- **Contextual retrieval** based on relevance
- **Onboarding support** for new projects

### Development Patterns

**Adding New Languages:**
1. Create language server class in `src/solidlsp/language_servers/`
2. Add to Language enum in `src/solidlsp/ls_config.py`
3. Update factory method in `src/solidlsp/ls.py`
4. Create test repository in `test/resources/repos/<language>/`
5. Write test suite in `test/solidlsp/<language>/`
6. Add pytest marker to `pyproject.toml`

**Adding New Tools:**
1. Inherit from `Tool` base class in `src/serena/tools/tools_base.py`
2. Implement required methods and parameter validation
3. Register in appropriate tool registry
4. Add to context/mode configurations

### Testing Strategy
- Language-specific tests use pytest markers
- Symbolic editing operations have snapshot tests
- Integration tests in `test_serena_agent.py`
- Test repositories provide realistic symbol structures

### Configuration Hierarchy

Configuration is loaded from (in order of precedence):
1. Command-line arguments to `serena-mcp-server`
2. Project-specific `.serena/project.yml`
3. User config `~/.serena/serena_config.yml`
4. Active modes and contexts

### Key Implementation Notes

- **Symbol-based editing** - Uses LSP for precise code manipulation
- **Caching strategy** - Reduces language server overhead
- **Error recovery** - Automatic language server restart on crashes
- **Multi-language support** - 19 languages with LSP integration (including Vue)
- **MCP protocol** - Exposes tools to AI agents via Model Context Protocol
- **Async operation** - Non-blocking language server interactions

### Working with the Codebase

- Project uses Python 3.11 with `uv` for dependency management
- Strict typing with mypy, formatted with black + ruff
- Language servers run as separate processes with LSP communication
- Memory system enables persistent project knowledge
- Context/mode system allows workflow customization

---

## Claude Code Internal Tools

**Skills** (/test-driven-development):
- Internal to Claude Code, not available to other agents
- Provides language-specific TDD commands (pytest, cargo, stack, jest)
- Follow skill for RED→GREEN→COMMIT→REFACTOR cycle

**Native Read/Write/Edit**:
- Internal file operations for convenience
- Prefer MCP Serena tools for portability when possible

---

## Prohibited Tools (Constitutional)

**EnterPlanMode**: ⛔ NEVER USE - Constitutional violation

EnterPlanMode bypasses constitutional gates:
- Skips think_about_task_adherence checkpoint
- Skips AI Panel critique (MANDATORY)
- Uses plan file instead of TodoWrite
- Doesn't create feature branch
- Weaker approval flow

**Correct Approach**: When planning is needed, follow M3 PLAN ONLY macro with all constitutional gates.

---

## Web Scraping Tools (scraper-mcp PRIMARY)

**Canonical Rule**: NEVER use WebFetch. ALWAYS use scraper-mcp for web content retrieval.

**Why scraper-mcp is PRIMARY**:
- JavaScript rendering via Playwright (`render_js=true`) - captures SPA/dynamic content
- CSS selectors - target specific content, skip navigation/footers
- Batch URLs - multiple pages in single call
- 2-3x more token-efficient than WebFetch (no AI processing overhead)
- Returns exactly requested format (markdown, text, HTML, links)

**Available Tools**:
| Tool | Returns | Use Case |
|------|---------|----------|
| `mcp__scraper__scrape_url` | Markdown | Documentation, articles |
| `mcp__scraper__scrape_url_text` | Plain text | Data extraction |
| `mcp__scraper__scrape_url_html` | Raw HTML | Structured parsing |
| `mcp__scraper__scrape_extract_links` | Links | Discovery, crawling |

**Critical Parameters**:
```python
mcp__scraper__scrape_url(
    urls=["https://code.claude.com/docs/en/hooks"],
    render_js=true,  # MANDATORY for SPAs, modern docs
    css_selector=".content",  # Target main content only
    timeout=30,
    max_retries=3
)
```

**Workflow Pattern**:
1. WebSearch (find URLs) → 2. scraper-mcp (extract content) → 3. process results

**When to Use WebFetch** (FALLBACK ONLY):
- scraper-mcp unavailable or failing
- Need AI interpretation of ambiguous content
- Simple static pages where AI summary is the goal

**Anti-Pattern**: Using WebFetch when scraper-mcp is available = CRITICAL violation (wrong tool selection)

---

## Contract Testing Configuration (CL10)

**File Locations**:
- Contracts: `contracts/<dependency>.contract.py`
- Verification: `tests/contracts/test_<dependency>_contract.py`
- Mocks: `tests/mocks/<dependency>_mock.py` (derived from contract)

**pytest Markers**:
- `@pytest.mark.contract` - Contract verification tests
- Run: `pytest -m contract` - Verify all contracts against real providers

**CI Integration**:
- Contract tests run in CI pipeline before deployment
- Mock drift (contract failure) blocks deployment
- Use `--run-contracts` flag for local verification

**Migration Status** (existing mocks requiring contracts):
- [ ] Database contracts (psycopg2, semantic_search schema)
- [ ] External API contracts (if any)
- [ ] File system contracts (if any)

**Example Contract** (from orphaned_at incident):
```python
# contracts/database.contract.py
MEMORY_EVENTS_SCHEMA = {
    "table": "semantic_search.memory_events",
    "columns": ["id", "commit_hash", "parent_hash", "orphaned_at", ...]
}
```

---

## TDD Skill Integration

**Operational Precedence**: TDD skill has priority for detailed TDD cycle procedures

**Constitutional Framework**: Provides workflow integration (M4 macro), response templates, evidence format standards

**Constitutional Laws Reinforced**: CL2 (completion gates), CL5 (human approval), CL6 (TDD enforcement) - intentionally duplicated between constitutional framework and skill for emphasis

**Usage**:
- **QS1 TDD/BDD**: Follow `/test-driven-development` skill for RED→GREEN→COMMIT→REFACTOR cycle
- **Language Commands**: Skill provides pytest, cargo, stack, jest commands
- **Evidence Format**: Use canonical format `[TEST:module::name=PASS/FAIL]` even when skill shows alternate formats
- **Response Template**: Use MANDATORY constitutional template (STATE/NEXT MACRO/ACTIONS/EVIDENCE/BLOCKERS) during TDD work

**M4 Integration**:
```
- M4 START TDD CYCLE:
  1. think_about_task_adherence checkpoint
  2. ↪ test-writer (RED) | See SUB-AGENT INVOCATION GUIDE
  3. ↪ coder (GREEN) | See SUB-AGENT INVOCATION GUIDE
  4. 🔄 Iteration cycle if tests fail | See Decision Matrix
  5. ↪ constitutional-code-auditor (compliance)
  6. AI Panel review → apply ALL feedback
  7. Use constitutional response template (not skill template)
  8. Use canonical evidence format (F:path T:test C:hash COV:% O:output)
```

---

## SUB-AGENT INVOCATION GUIDE

### Adversarial TDD Architecture

**Coordinator Role**: Orchestrate test-writer → coder → iteration cycle

**Coordination Pattern Distinction**:
- **This section**: Sub-agent coordination (test-writer/coder invocation within TDD workflow)
- **Orchestrator-Agent coordination**: Different pattern - task delegation between orchestrator and agent
  - Use `/agent-coordination` skill for orchestrator-agent 6-step pattern
  - Use SUB-AGENT INVOCATION GUIDE (below) for test-writer/coder invocation

**When to use which**:
- Orchestrator assigns task to YOU → `/agent-coordination` (you are the agent receiving task)
- YOU orchestrate test-writer/coder → SUB-AGENT INVOCATION GUIDE (you are the coordinator)
- YOU are orchestrator delegating to agent → `/agent-coordination` (you are orchestrator assigning task)

**Decision Matrix**:
| Tests Pass? | test_sound? | impl_sound? | Action |
|-------------|-------------|-------------|--------|
| ❌ | True | False | ↪ refactor-coder |
| ❌ | False | True | ↪ refactor-test-writer |
| ❌ | False | False | Escalate → user |
| ✓ | N/A | N/A | Proceed M5 |

### test-writer Invocation (M4.2 RED)

**ADVERSARIAL TDD ENFORCEMENT** (Emphasize in prompt):
- test-writer BLIND to implementation → Guidance = BEHAVIOR only (WHAT, not HOW)
- Theater test check: "Can impl be wrong and test pass?" If YES → REJECT
- Deterministic problems: Exact values, not ranges (e.g., `result = 669171001` not `result > 0`)
- Prompt template: "You are BLIND to implementation. Guidance describes WHAT behavior, never HOW to implement. For math: exact values."

**Context to Pass**:
```yaml
task_description: "Feature description"
requirements: |
  REQ-XXX-NNN: Specific requirements
tsr_template: |
  # Test Specification Review
  [Use canonical 5-section format]
constraints:
  - Data isolation (ephemeral only)
  - Compatibility requirements
```

**Expected Output**:
- Test files with self-documenting error messages
- AI Panel ONESHOT validation summary
- Coverage map (which requirements tested)

**Error Message Quality Gate** (5-point standard):
1. What failed (test name)
2. Why (requirement violated)
3. Expected behavior (spec)
4. Actual behavior (what happened)
5. Guidance (behavioral only - WHAT, not HOW)

**Point #5 Guidance Format** (MANDATORY - Constitutional Amendment):
- ❌ **PROHIBITED**: Implementation hints (if/else patterns, function names, file paths, line numbers, code patterns)
- ✅ **REQUIRED**: Behavioral contracts (exact match required, validation rules, observable requirements)
- ✅ **REQUIRED**: Observable side effects (logging level, error types, state changes)

**Examples**:

**BAD Guidance (Prescriptive - violates adversarial separation)**:
```
"Use if header_value == '2025-03-26' { new_protocol } else { old_protocol }.
Check validate_mcp_protocol_version() at line 61."
```

**GOOD Guidance (Behavioral - preserves adversarial separation)**:
```
"Protocol validation MUST use exact string match. Any non-exact value → old protocol.
MUST log malformed versions at WARN level for monitoring.
Implementation free to choose: equality check, regex, parse+validate, etc."
```

**Rationale**: AI agents will copy code-like guidance verbatim (token efficiency bias). Behavioral guidance forces exploration and prevents theater tests.

### coder Invocation (M4.3 GREEN)

**Context to Pass**:
```yaml
task_description: "Feature description"
requirements: |
  [Same as test-writer]
error_messages: |
  [ACTUAL test output - full text]
constraints:
  - Minimal implementation (YAGNI)
  - DRY (use existing utilities)
```

**Adversarial Constraint**: 🚫 test source code | ✓ error messages only

**Expected Output**:
- Implementation that makes tests pass
- AI Panel ONESHOT (if design ambiguity)
- git commit (WHY/EXPECTED format)

### Iteration Cycle

**When tests fail after coder**:

1. **Coordinator Analysis**:
```python
# Run tests → get error messages
# Analyze: Are error messages clear?
# Analyze: Does implementation match error guidance?

if error_messages_unclear:
    test_sound = False  # → refactor-test-writer
elif implementation_wrong:
    test_sound = True
    impl_sound = False  # → refactor-coder
else:
    # Both sound but incompatible
    escalate_to_user()
```

2. **refactor-test-writer** (test_sound=False):
- Full context (tests + impl + requirements + coordinator explanation)
- Fix test to correctly validate requirement
- Maintain error message quality

3. **refactor-coder** (impl_sound=False):
- Full context (tests + impl + requirements)
- Fix implementation to pass tests
- Minimal changes only

### Orchestrator Test Quality Audit

**Before approving test-writer output**:
- [ ] Guidance = BEHAVIOR only (no "build X", "calculate Y", algorithm hints)
- [ ] Deterministic problems use exact values (not ranges/approximations)
- [ ] Theater test check passed: "Can impl be wrong and test pass?" = NO
- [ ] All 5-point error messages present, Point #5 behavioral

**Reference**: See ~/.claude/skills/theater-test-detection/ for detection methodology

### Evidence Recording

**Per Sub-Agent Invocation**:
```
F:.claude/agents/test-writer.md:1-50 (invoked)
T:module::test_name=PASS
C:hash (test-writer output)

F:.claude/agents/coder.md:1-50 (invoked)
T:module::test_name=PASS (N/N passing)
C:hash (coder output)
COV:X%
```

---

## Serena Think Tools → AI Panel Integration

**Claude Code Enhancement**: Automates evidence gathering via Serena think tools

**Automated Checkpoint Flow**:
1. Call Serena think tool → automatic reflection
2. If pass → automatically triggers evidence gathering
3. Gather evidence per AI Panel Evidence Protocol (actual code, not summaries)
4. Submit to AI Panel with `enable_conversation=true`
5. Apply ALL feedback before proceeding per CL5 (human approval)

**Think Tool Integration Details**:

**`think_about_collected_information`** (M1, M2):
- Purpose: Validate information sufficiency after discovery
- Questions: "Where am I?" "What am I missing?" "Can I start planning?"
- **No AI Panel integration** (discovery phase only)

**`think_about_task_adherence`** (M3, M4):
- Purpose: Validate task alignment before planning/implementation
- Questions: "Am I solving the right problem?" "Does plan align with user request?"
- **AI Panel Integration**:
  1. Call think tool (automatic reflection)
  2. If pass → gather evidence:
     - M3: Read plan file, user requirements, constraints
     - M4: Read approved plan, run `git diff`, note deviations
  3. Submit to AI Panel:
     - M3: `critique_implementation_plan`
     - M4: `check_plan_adherence` + `critique_code`
  4. Apply ALL feedback before proceeding

**`think_about_whether_you_are_done`** (M5):
- Purpose: Validate completion gates before claiming done
- Questions: "Tests pass?" "AI Panel reviewed?" "Evidence recorded?" "User approval?"
- **AI Panel Integration**:
  1. Call think tool (completion self-assessment)
  2. If pass → gather final evidence:
     - Run test suite + coverage
     - Get `git diff main...feature/<branch>`
     - Review AI Panel conversation history
  3. Submit to `critique_code` (final) with conversation_id from M4
  4. Apply ALL feedback before claiming done

**Evidence Gathering Automation**:
```python
# Get actual code (not summaries)
find_symbol(
    name_path="ClassName/method_name",
    relative_path="src/file.rs",
    include_body=true
)

# Get symbol overview for context
get_symbols_overview(
    relative_path="src/file.rs"
)

# Get git diff for Turn 2+ submissions
bash("git show <commit>")
bash("git diff main..feature/branch")
```

**Automatic Integration** (Claude Code advantage):
- Serena think tools → check pass/fail
- If pass → agent uses Serena tools to gather evidence
- Agent submits to AI Panel with actual code
- User never needs to remind "send actual code"

---

## Copilot CLI (Fast Oneshot Validation)

**Purpose**: Quick expert consultation without full AI Panel overhead

**Tool**: `copilot -p "natural language query"` (oneshot mode ONLY in shell environment)

**Positioning**:
- **NOT a substitute for AI Panel** - AI Panel provides structured multi-model analysis
- Copilot is a faster, smaller oneshot version for quick validation
- Use AI Panel for debugging (debug_assistance), architectural decisions, comprehensive reviews
- Use copilot for sanity checks, prompt formulation, simple validation

**Capabilities**:
- ✅ Quick sanity checks ("Is this logic correct?")
- ✅ Prompt formulation help
- ✅ Simple validation queries
- ✅ Type/syntax verification
- ❌ **Cannot use interactive mode** (no stdin/stdout interaction in tool environment)
- ❌ **Cannot use `--continue`** (no session persistence between tool calls)
- ❌ **Cannot edit files** (read-only consultation)

**Syntax Constraints**:
- Single-line queries only (no multi-line paragraphs)
- No markdown formatting (no backticks, no code blocks)
- Escape special characters if needed
- Content must fit in quoted string: `copilot -p "query here"`

**Model Selection** (from `copilot --help`):
```
-m, --model <MODEL>  Specific model to use [default: claude-3-7-sonnet-20250219]
    --opus           Use Claude Opus (highest capability)
    --sonnet         Use Claude Sonnet (balanced)
    --haiku          Use Claude Haiku (fastest)
```

**Token Economics**:
- Copilot oneshot: ~100-200 tokens
- AI Panel ONESHOT: ~1,500 tokens
- AI Panel PARALLEL: ~15,000 tokens
- **Result**: Copilot is 7.5x cheaper than AI Panel ONESHOT, 75x cheaper than PARALLEL

**When to Use Copilot** (vs AI Panel):
```
DECISION TREE:
├─ Stuck on bug/blocker? → AI Panel debug_assistance (MANDATORY per CL3)
├─ Architectural decision? → AI Panel (MANDATORY)
├─ Need multi-model consensus? → AI Panel PARALLEL
├─ Complex debugging? → AI Panel debug_assistance (structured sections)
├─ Quick "is this correct?" → copilot -p "query"
├─ Prompt formulation help → copilot -p "How should I prompt..."
└─ Simple validation → copilot -p "query"
```

**CL3 Enforcement**: DO NOT use copilot for repeated debugging attempts. If stuck (bugs, blockers, unexpected behavior), use AI Panel debug_assistance FIRST. Copilot is for quick validation, not iterative problem-solving.

**Copilot Flags** (from `copilot --help`):
- `-p, --prompt <PROMPT>`: Natural language instruction
- `-c, --continue`: Continue previous conversation (⚠️ NOT available in tool environment)
- `-f, --file <FILE>`: Attach file context
- `-i, --interactive`: Interactive mode (⚠️ NOT available in tool environment)
- `--stream`: Stream responses (default: true)
- `--no-stream`: Disable streaming

**Examples**:

```bash
# Quick validation (✅ appropriate use)
copilot -p "Is test expecting successful_creations==1 wrong for create_or_get pattern?"

# Prompt formulation (✅ appropriate use)
copilot -p "How should I prompt refactor-test-writer to fix stubbed tests while preserving error messages?"

# Type checking (✅ appropriate use)
copilot -p "PostgreSQL pg_advisory_xact_lock returns VOID or bool?"

# With file context (✅ appropriate use)
copilot -p "Does this test logic correctly verify concurrent session creation?" -f tests/session_tests.rs

# Complex debugging (❌ should use AI Panel debug_assistance)
copilot -p "Why does my advisory lock allow duplicates across 10 concurrent tasks?"
# CORRECT: Use AI Panel debug_assistance with structured sections instead
```

**Integration with M4 Workflow**:
```python
# M4.2 RED: Formulating refactor-test-writer prompt
copilot -p "How should I prompt refactor-test-writer to replace test stubs with real SessionManager calls?"
# → Get 7-point strategy → Invoke refactor-test-writer with refined prompt

# M4.3 GREEN: Validating test logic during iteration
copilot -p "Is test expecting 1 success wrong? Should it verify all tasks succeed with same session_id?"
# → Confirm test logic is flawed → Fix test instead of implementation
```

**Token Efficiency Evidence** (Cycle 6 Phase 2):
- Prompt formulation query: 180 tokens (vs 1.5K for AI Panel ONESHOT)
- Test logic validation: 150 tokens (vs 1.5K for AI Panel ONESHOT)
- Total savings: ~2.7K tokens (90% reduction vs AI Panel)
- **Result**: Enabled 2 critical validations without AI Panel overhead

---

## GitHub CLI Token Configuration (SPINE-Compliant)

**Security Model**: Two-token architecture preserving SPINE isolation.

| Token | Scope | Storage | Use Case |
|-------|-------|---------|----------|
| Fine-grained (default) | User's private repos only | `gh auth` keyring | Daily workflow, private repo PRs |
| Classic `public_repo` | Public repos only | `biosecret` | Upstream PRs on public repos |

**Trigger**: Creating PRs on **public upstream repos you don't own** (e.g., `oraios/serena`).

**Command Pattern**:
```bash
# Upstream PR creation (public repos)
GH_TOKEN=$(~/bin/biosecret get gh-public-repo-token ketema) gh pr create \
  --repo <upstream-org>/<repo> \
  --head <your-fork>:<branch> \
  --base main \
  --title "..." --body "..."

# Example: PR to oraios/serena
GH_TOKEN=$(~/bin/biosecret get gh-public-repo-token ketema) gh pr create \
  --repo oraios/serena \
  --head ketema:fix/my-branch \
  --base main \
  --title "fix: description" --body "$(cat <<'EOF'
## Summary
...
EOF
)"
```

**Default gh commands** (no prefix needed): Use keyring token for user's repos.

**Anti-Pattern**: Using `public_repo` token for private repo operations = SPINE violation.

**PR Edits** (use REST API, not GraphQL):
```bash
# gh pr edit uses GraphQL → requires read:org (we don't have)
# Use REST API instead:
GH_TOKEN=$(~/bin/biosecret get gh-public-repo-token ketema) gh api \
  --method PATCH /repos/<org>/<repo>/pulls/<number> \
  -f body="new body" -f title="new title"
```

**Token Renewal**: Classic PATs expire. Regenerate via GitHub Settings → Tokens (classic), store with `biosecret set gh-public-repo-token ketema`.

---

## Response Template (Constitutional Adherence)

Use MANDATORY response template per constitutional requirement:

```
STATE: <workflow state>
BRANCH: <git branch or "not a git repo">
TOKEN_BUDGET: <current>/<total> (<percent>%) - <remaining> remaining
COMPACT_REMINDER: <if 75-80%, display "⚠️ COMPACT NOW: Run /compact to prevent auto-compact failure">
NEXT MACRO: <deterministic macro>

ACTIONS:
1. ...
2. ...

EVIDENCE:
C:hash (if commits)

F:path:lines
F:path2:lines

T:module::test=STATUS
COV:X%
O:snippet

Or "none" if no evidence

BLOCKERS: <missing info or none>
```

---

## Evidence Format (Constitutional Adherence)

Use canonical compressed format: F:path:lines T:module::name=STATUS C:hash COV:X% O:snippet

TDD Skill may show alternate formats - always record using canonical constitutional format

---

## Workflow Example

**M3 → M4 → M5 with Claude Code Automation**

### M3: Plan with Automation

```python
# 1. User: "Implement JWT authentication"

# 2. Agent creates plan (TodoWrite)

# 3. Agent calls think_about_task_adherence
# → Automatic reflection: "Am I solving the right problem?"
# → Pass: Yes, plan aligns with user request

# 4. Agent automatically gathers evidence using Serena tools
read_memory("user-preferences-and-workflow")  # Context
find_symbol("AuthHandler", include_body=true)  # Existing patterns
bash("git log --oneline -10")  # Recent work

# 5. Agent submits to AI Panel
conversation_id_m3 = critique_implementation_plan(
    enable_conversation=true,
    sections={
        context: "<from memory>",
        plan: "<ACTUAL plan from TodoWrite>",
        requirements: "Implement JWT authentication",
        constraints: "<from codebase analysis>",
        thinking: "Is this plan comprehensive? Any security gaps?"
    }
)

# 6. AI Panel provides critique → agent applies ALL feedback
```

### M4: Implementation with Automation

```python
# 1. Agent follows /test-driven-development skill (RED→GREEN→COMMIT→REFACTOR)

# 2. After commit, agent calls think_about_task_adherence
# → Automatic reflection: "Am I implementing what was approved?"
# → Pass: Yes, following approved plan

# 3. Agent automatically gathers evidence
read_file("approved_plan.md")  # From M3
bash("git diff main..feature/jwt-auth")  # Actual changes

# 4. Agent submits to AI Panel (check adherence)
check_plan_adherence(
    enable_conversation=true,
    conversation_id=conversation_id_m3,  # AI Panel knows the plan!
    sections={
        approved_plan: "<from M3>",
        current_implementation: "git log summary",
        implementation_code: "$(git diff main..feature/jwt-auth)",  # 80% token savings!
        adherence_focus: "JWT implementation, security best practices",
        deviation_concerns: "None"
    }
)

# 5. Agent submits to AI Panel (code critique)
conversation_id_m4 = critique_code(
    enable_conversation=true,
    sections={
        code_implementation: "$(git show a3f2c1b)",
        review_focus: "Security, error handling, test coverage",
        ...
    }
)

# 6. Apply ALL feedback
```

### M5: Final Validation with Automation

```python
# 1. Agent calls think_about_whether_you_are_done
# → Automatic reflection: "Are completion gates met?"
# → Check: Tests pass? Coverage >85%? AI Panel reviewed?
# → Pass: All gates satisfied

# 2. Agent automatically gathers final evidence
bash("cargo test --all")  # Test results
bash("git diff main...feature/jwt-auth")  # All changes

# 3. Agent submits to AI Panel (final critique)
critique_code(
    enable_conversation=true,
    conversation_id=conversation_id_m4,  # 80% token savings!
    sections={
        code_implementation: "$(git diff main...feature/jwt-auth)",
        review_focus: "Final validation - completeness, quality gates",
        ...
    }
)

# 4. Apply ALL feedback → Update memory → Done
```

**Token Efficiency**:
- M3: 10K tokens (full plan)
- M4 adherence: 3K tokens (AI Panel knows plan from M3)
- M4 code: 8K tokens (first code review)
- M5 final: 2K tokens (AI Panel knows code from M4)
- **Total**: 23K tokens vs 40K without automation (42% savings)

---

## Context Window Management (Claude Code)

**Base Protocol**: Follow constitutional context management protocol for universal handoff (proactive handoff at 80-90% usage)

**Claude Code-Specific**:

| Aspect | PreCompact Hook (Current) | Proactive Handoff (Required) |
|--------|---------------------------|------------------------------|
| **Trigger** | 190k tokens (95%) | 160k-180k tokens (80-90%) |
| **Buffer** | 10k tokens | 20-40k tokens |
| **Mode** | Emergency save | Controlled transition |
| **Recovery** | Manual `/restore-context` | Explicit handoff message |
| **Effectiveness** | Minimal context captured | Comprehensive state preservation |

**Compaction**: Claude Code's automatic context truncation when approaching token limit - "devastating to recall" (user), cannot be disabled

**Token Monitoring**: Watch for `<system_warning>Token usage: X/200000</system_warning>` messages

**Compaction Recovery Protocol**:
- If compaction occurs (sudden token drop from 190k → <100k), invoke `/agent-coordination` skill
- Read "Restart Recovery" section for memory-based protocol restoration
- Steps: Read protocol, read session state, read latest macro checkpoint, notify orchestrator of recovery (if mid-task)
- Reference: /agent-coordination skill → Restart-Proof Behavior section

**Specific Checks** (extend CL4):
- Before Sequential Thinking (5-15k): trigger if usage >185k
- Before AI Panel PARALLEL (15k): trigger if usage >175k
- Before large file reads (>10k): trigger if usage >175k

**PreCompact Hook**: Safety net at 95% - saves to `.serena/memories/auto-compact-context-save.md` - use only if proactive handoff missed

**Post-Compaction Status Protocol** (MANDATORY):
After ANY compaction event, the FIRST response MUST include:
```
POST-COMPACTION STATUS:
- Memory file found: yes/no
- Memory loaded: yes/no
- Context recovered: [brief summary of what was restored, or "none - manual /restore-context needed"]
```

**Detection**: Compaction indicated by `<session-context type="compact">` in system messages
**Action**:
1. Check if memory file path was provided in session-context
2. If yes: Read the memory file using Serena `read_memory` tool
3. Report status in first response using format above
4. If no memory path provided: Report "Memory file found: no" and suggest `/restore-context`

**Rationale**: User needs visibility into whether context was automatically restored or manual intervention required

---

## Agent Coordination

**When Needed**:
- **Orchestrator**: Delegating task to specialized agent
- **Agent**: Completing task and notifying orchestrator
- **Either**: Recovering protocol after compaction

**Skill**: `/agent-coordination` (6-step bidirectional pattern)

**Invocation Triggers**:
- Orchestrator: "I need to delegate task X to agent" → `/agent-coordination`
- Orchestrator: "Waiting for agent completion" → `/agent-coordination` (verify no polling)
- Agent: "Task complete, need to notify orchestrator" → `/agent-coordination`
- Either: "What's the tmux command for sending prompts?" → `/agent-coordination`
- Recovery: "Compaction occurred, how do I restore protocol?" → `/agent-coordination`

**Pattern Overview** (see skill for full details):

**Orchestrator Steps**:
1. **Write task** to `.serena/memories/task-[id].md` with requirements, context, constraints
2. **Send prompt** via tmux:
   ```bash
   tmux send-keys -t claude-orchestrator.1 "TASK: [description]. Read: task-[id].md"
   tmux send-keys -t claude-orchestrator.1 C-m
   ```
3. **Verify ONCE** via `tmux capture-pane -t claude-orchestrator.1 -p | tail -20`, then STOP (no polling)
6. **Read response** from `ametek-claude/.serena/memories/task-[id]-response.md`, audit compliance

**Agent Steps**:
4. **Perform task**, write response to `ametek-claude/.serena/memories/task-[id]-response.md`
5. **Send completion prompt** via tmux:
   ```bash
   tmux send-keys -t claude-orchestrator.0 "TASK COMPLETE: [summary]. Read: task-[id]-response.md"
   tmux send-keys -t claude-orchestrator.0 C-m
   ```

**Key Principles**:
- Bidirectional: Both orchestrator and agent use same skill (different steps)
- No polling between Steps 3-5 → 75% token savings (~1,200 vs ~3,000+ tokens)
- Memory-based handoff is restart-proof (survives compaction)
- Constitutional format mandatory: STATE/ACTIONS/EVIDENCE/BLOCKERS
- Tmux pattern: Send text first, C-m second (NEVER combined)

**Pane Targets**:
- Orchestrator pane: `claude-orchestrator.0`
- Agent pane: `claude-orchestrator.1`

**Token Efficiency Evidence**:
- Euler #26 task: ~1,200 tokens (6-step with one verification)
- Alternative (polling every 2 minutes): ~3,000+ tokens
- Savings: 60% reduction per task

**Reference**: Invoke `/agent-coordination` skill for complete protocol, tmux commands, memory paths, recovery procedures.

---

## Deployment

**AI Panel Local Deployment** (Purpose-Built Agent):
- **When user says**: "Deploy the AI Panel locally" or "Deploy AI Panel MCP Server locally"
- **Action**: ↪ general-purpose agent with prompt: "Deploy AI Panel MCP Server locally with autonomous script discovery and execution"
- **Rationale**: Deployment complexity (script location, environment validation, Docker orchestration) requires autonomous agent
- **Agent Capabilities**: Script discovery, dependency checks, build execution, container health verification
- **Output**: Container ID, health status, or actionable error

**Cloud Run Deployment** (Purpose-Built Agent):
- **When user says**: "Deploy to Cloud Run" or "Deploy MCP Server to cloud" or "Cloud deployment"
- **Action**: ↪ general-purpose agent with prompt: "Deploy MCP Server to Cloud Run with comprehensive validation, smoke tests, and automatic rollback"
- **Rationale**: Cloud deployment requires multi-phase orchestration (GUARDED, LINT, BUILD, DEPLOY, TESTS, AUDITABLE) with production safety guarantees
- **Agent Capabilities**:
  - Pre-deployment validation (15 comprehensive checks)
  - Cloud Build orchestration with error recovery
  - Cloud Run deployment with secret management
  - Comprehensive smoke tests (13 tests)
  - Automatic rollback on failure
  - Deployment receipt generation for audit trail
- **Script**: `deployment/scripts/deploy-cloud.sh` (ONE-COMMAND deployment)
- **Principles**: GUARDED, TESTS, LINT, DETERMINISTIC, AUDITABLE (matching local deployment quality)
- **Output**: Service URL, revision ID, deployment receipt, or rollback confirmation

**Other Deployments** (Operational Procedures):
- **When user says**: "Deploy [other-service] [target]"
- **Action**: Query →serena:deployment-procedures for service+target → Execute command → Report outcome
- **Example**: Database migrations, test infrastructure, monitoring services

**Constitutional Principle**: Specialized agents take precedence over direct execution for complex operational tasks. Use agent delegation when task involves discovery, validation, or multi-step orchestration.

**Script Details**: rust/mcp_workspace/deployment/README.md

---

## SYMBOLIC NOTATION GUIDE

### Formal Grammar

**Structure**: `↪ <agent> | <prohibitions> | <permissions> | → <output>`

**Context Rules Format**:
- `🚫 <resource>`: Prohibited access (hard constraint)
- `✓ <resource>`: Permitted access (explicit allowlist)
- **Default**: Deny (all resources not in ✓ list are prohibited)
- `|`: Separator (AND clause, all conditions apply)

**Parse Example**:
```
↪ test-writer | 🚫 impl | ✓ req+TSR | → err-msgs (5-point)
```

**Interpretation**:
1. Invoke test-writer sub-agent (MANDATORY)
2. Prohibition: Implementation code access blocked
3. Permission: Requirements + TSR documents ONLY
4. Expected output: Error messages (5-point standard)
5. Implicit: All other resources prohibited (tests, logs, context)

### Scope

**MANDATORY Symbolic Notation**:
- M1-M5 coding macros (high-frequency invocations)
- Evidence recording (F:path T:test C:hash)
- Sub-agent invocations in workflows

**PROHIBITED Symbolic Notation**:
- Conversational contexts (planning, teaching, discussion)
- Explanatory rationale (WHY explanations)
- User-facing communication (responses, questions)

**Rationale**: Symbols for execution efficiency, prose for understanding/creativity.

### Symbol Vocabulary

**Invocation**: `↪ agent-name`
**Access Control**: `🚫 prohibited | ✓ allowed`
**Workflow**: `→ delegates-to`
**Fast-Path**: `⚡ skip-if-simple`
**Iteration**: `🔄 repeat-until-pass`
**Violation**: `⛔ constitutional-stop`

### Hybrid Notation Examples

**M4 Invocation (Coding Macro)**:
```markdown
2. **MANDATORY**: ↪ test-writer | 🚫 impl | ✓ req+TSR → err-msgs (5-point)
   - ⛔ Coordinator SHALL NOT write tests directly
   - Rationale: Adversarial separation forces self-documenting errors (77/77 success)
```
**Why Hybrid?**
- Symbolic: Execution directive (token-efficient)
- Enforcement: Constitutional prohibition (unambiguous)
- Rationale: Learning context (preserves "WHY")

**Evidence Recording (Coding Macro)**:
```
F:.claude/agents/test-writer.md:1-50 (invoked)
T:auth::jwt=PASS (77/77)
C:a3f2c1b
COV:87%
```

**Conversational Context (Prose REQUIRED)**:
```markdown
User: "Why do we use test-writer instead of writing tests directly?"

Agent: "The adversarial TDD architecture enforces a critical separation:
test-writer cannot see implementation code, and coder cannot see test source.
This constraint forces test-writer to create self-documenting error messages,
because that's the ONLY way coder can understand what to implement.

The result? 100% test success rates (77/77 in Project Euler 957) because
error messages become genuine specifications, not implementation-aware checks."
```
**Why Prose?** Teaching/explanation requires conversational clarity, not symbols.

---

## TOKEN EFFICIENCY MEASUREMENT PROTOCOL

**Purpose**: Validate token savings claims with reproducible measurements

**Baseline Definition**: Full prose invocation measured via Claude API token count

**Measurement Procedure**:
1. Count tokens in full prose sub-agent invocation template
2. Count tokens in symbolic notation equivalent
3. Calculate: (baseline - symbolic) / baseline × 100

**Project Euler 957 Evidence**:
- Full prose M4 invocation: ~450 tokens
- Symbolic M4 invocation: ~150 tokens
- Per-invocation savings: 67%
- Total invocations: 77 (RED + GREEN phases)
- Total savings: 77 × 300 tokens = 23,100 tokens
- Project total: 70K tokens vs projected 105K (33% overall savings)

**Validation Protocol**:
- Measure actual token counts in next 3 M4 invocations
- Compare symbolic vs prose equivalents
- Update measurements if variance >10%

**Token Counting Method**:
- Use Claude API token count (official)
- Include all context passed to sub-agent
- Exclude sub-agent internal consumption (separate budget)
