# CLAUDE CODE EXTENSIONS TO MCP-BASED CONSTITUTION

**Precedence**: Constitutional principles (CL1-CL8, QS1-QS6, M1-M5) are foundational. If conflict, system prompt ALWAYS overrides.

---

## Serena Commands

```bash
uv run poe format      # Format (BLACK+RUFF) - ONLY allowed
uv run poe type-check  # mypy - ONLY allowed
uv run poe test        # pytest (excludes java/rust default)
uv run poe test -m "python or go"  # Specific markers
uv run poe lint        # Check style
```

**Markers**: python, go, java, rust, typescript, vue, php, perl, powershell, csharp, elixir, terraform, clojure, swift, bash, ruby, ruby_solargraph, snapshot

**Always run format, type-check, test before completing tasks.**

---

## Serena Architecture

Dual-layer agent toolkit: SerenaAgent orchestrates projects/tools/memory; SolidLanguageServer wraps LSP for 19 languages.

**Key paths**: `src/serena/tools/` (file, symbol, memory, config, workflow), `src/solidlsp/` (language servers), `.serena/memories/` (knowledge persistence)

**Config precedence**: CLI args → `.serena/project.yml` → `~/.serena/serena_config.yml` → modes/contexts

---

## Claude Code Internal Tools

- **Skills** (`/test-driven-development`): TDD commands (pytest, cargo, stack, jest)
- **Native Read/Write/Edit**: Prefer MCP Serena tools for portability

---

## Prohibited Tools (Constitutional)

**EnterPlanMode**: ⛔ NEVER USE - bypasses think_about_task_adherence, AI Panel critique, TodoWrite, feature branch. Use M3 PLAN ONLY macro instead.

---

## Web Scraping (scraper-mcp PRIMARY)

**Rule**: NEVER WebFetch. ALWAYS scraper-mcp.

| Tool | Returns | Use |
|------|---------|-----|
| `scrape_url` | Markdown | Docs |
| `scrape_url_text` | Text | Extract |
| `scrape_url_html` | HTML | Parse |
| `scrape_extract_links` | Links | Crawl |

**Critical**: `render_js=true` for SPAs, `css_selector` for targeting.

**Fallback**: WebFetch only if scraper-mcp fails or need AI interpretation.

---

## Contract Testing (CL10)

**Paths**: `contracts/<dep>.contract.py` → `tests/contracts/test_<dep>_contract.py` → `tests/mocks/<dep>_mock.py`

**Run**: `pytest -m contract` | CI blocks on mock drift | `--run-contracts` for local

---

## Design by Contract (CL12)

**Library**: `icontract`

**Canonical Example** (MEMORIZE THIS FORMAT):
```python
def get_session(self, id: str) -> Session | None:
    """
    Retrieve session by identifier.

    PRE: id is non-empty string
    POST: Returns Session if id exists in registry, None otherwise
    INV: Registry state unchanged
    INV: No side effects
    """
```

**Type vs Contract** (CRITICAL DISTINCTION):
- ❌ `def get_session(id: str) -> Session | None:` ← Type hint = STRUCTURE only
- ✅ `PRE/POST/INV` in docstring ← Contract = BEHAVIOR

**Strict Constructionism**: Undeclared behavior = CONTRACT VIOLATION. All side-effects must be in POST.

**Test-Contract Traceability**: Every assertion traces to PRE/POST/INV spec.

| Question | Answer |
|----------|--------|
| Type hint = contract? | NO |
| Add logging without contract update? | NO - Strict Constructionism |
| Silent on side-effects? | Side-effects PROHIBITED |
| Tests reference specs? | YES - always |

**Extended Examples**: `/cl12-examples` skill or `~/.claude/examples/cl12-detailed.md`

---

## TDD Skill Integration

Follow `/test-driven-development` skill for RED→GREEN→COMMIT→REFACTOR.

**M4 Integration**:
1. think_about_task_adherence
2. ↪ test-writer (RED) | 🚫 impl | ✓ req+TSR
3. ↪ coder (GREEN) | 🚫 test-source | ✓ error-msgs
4. 🔄 Iteration if fail (Decision Matrix below)
5. ↪ constitutional-code-auditor
6. AI Panel review → apply ALL feedback

**Evidence**: `F:path:lines T:module::test=STATUS C:hash COV:%`

---

## SUB-AGENT INVOCATION GUIDE

**Coordination Patterns**:
- Orchestrator→Agent: `/agent-coordination` skill
- TDD sub-agents: This guide

**Decision Matrix**:
| Pass? | test_sound | impl_sound | Action |
|-------|------------|------------|--------|
| ❌ | T | F | ↪ refactor-coder |
| ❌ | F | T | ↪ refactor-test-writer |
| ❌ | F | F | Escalate → user |
| ✓ | - | - | M5 |

### test-writer (M4.2 RED)

**Constraints**: BLIND to impl | Guidance = BEHAVIOR only (WHAT, not HOW) | Deterministic = exact values

**5-Point Error Message** (CANONICAL EXAMPLE):
```python
assert len(session_id) == 36, (
    f"test_session_id_format FAILED | "      # 1. What failed
    f"REQ-SESSION-001 violated | "            # 2. Why (requirement)
    f"Expected: UUID v4 format (36 chars) | " # 3. Expected
    f"Actual: got {len(session_id)} chars | " # 4. Actual
    f"Guidance: MUST generate valid UUID v4"  # 5. Behavioral hint
)
```

**Theater Test Check**: "Can impl be wrong and test pass?" YES → REJECT

**Extended Templates**: `~/.claude/examples/error-message-templates.md`

### coder (M4.3 GREEN)

**Constraints**: 🚫 test-source | ✓ error-msgs only | YAGNI | DRY

**Output**: Implementation + AI Panel ONESHOT (if ambiguity) + WHY/EXPECTED commit

### Iteration

```python
if error_messages_unclear: test_sound=False → refactor-test-writer
elif implementation_wrong: impl_sound=False → refactor-coder
else: escalate_to_user()
```

---

## Think Tools → AI Panel Integration

**Flow**: Think tool → gather evidence (actual code) → AI Panel (`enable_conversation=true`) → apply ALL feedback

| Tool | When | AI Panel |
|------|------|----------|
| `think_about_collected_information` | M1/M2 | None |
| `think_about_task_adherence` | M3/M4 | `critique_implementation_plan` / `check_plan_adherence` |
| `think_about_whether_you_are_done` | M5 | `critique_code` (final) |

**Evidence**: `find_symbol(include_body=true)`, `git show`, `git diff` - never summaries.

**Workflow Examples**: `~/.claude/examples/workflow-m3-m4-m5.md`

---

## Copilot CLI

**Tool**: `copilot -p "query"` (oneshot only)

**Decision**:
- Bug/blocker → AI Panel `debug_assistance` (CL3)
- Architecture → AI Panel (MANDATORY)
- Quick validation → `copilot -p "..."`

**Constraints**: Single-line, no markdown, no interactive mode, no `--continue`

**Cost**: ~150 tokens vs AI Panel 1.5K-15K

---

## GitHub CLI Tokens

**Two-token model** (SPINE):
- Fine-grained (default): Private repos, `gh auth` keyring
- Classic `public_repo`: Public upstream PRs, `biosecret`

**Upstream PR**: `GH_TOKEN=$(~/bin/biosecret get gh-public-repo-token ketema) gh pr create --repo <upstream>/<repo> ...`

---

## Response Template (MANDATORY)

```
STATE: <workflow state>
BRANCH: <git branch>
TOKEN_BUDGET: <current>/<total> (<percent>%)
COMPACT_REMINDER: <if 75-80%: "⚠️ COMPACT NOW">
NEXT MACRO: <macro>

ACTIONS:
1. ...

EVIDENCE:
C:hash F:path:lines T:mod::test=STATUS COV:% O:snippet

BLOCKERS: <info> or "none"
```

---

## Evidence Format

Canonical: `F:path:lines T:module::name=STATUS C:hash COV:% O:snippet`

---

## Context Window Management

**Trigger**: 80-90% usage (160k-180k tokens)

**Checks before expensive ops**:
- Sequential Thinking (5-15k): >185k → trigger
- AI Panel PARALLEL (15k): >175k → trigger
- Large file reads (>10k): >175k → trigger

**Post-Compaction** (MANDATORY first response):
```
POST-COMPACTION STATUS:
- Memory file found: yes/no
- Memory loaded: yes/no
- Context recovered: [summary]
```

**Recovery**: Read `auto-compact-context-save.md` via Serena, or `/restore-context`

---

## Agent Coordination

**Reference**: `/agent-coordination` skill (6-step bidirectional pattern)

**Triggers**: Task delegation, completion notification, compaction recovery, tmux syntax

**Principles**: No polling (75% savings), memory-based (restart-proof), constitutional format

---

## Deployment

**AI Panel Local**: ↪ agent "Deploy AI Panel MCP Server locally..."
**Cloud Run**: ↪ agent "Deploy MCP Server to Cloud Run with validation, smoke tests, rollback"
**Other**: Query `→serena:deployment-procedures` → execute → report

---

## Symbolic Notation

**Grammar**: `↪ <agent> | 🚫 prohibited | ✓ allowed | → output`

**Symbols**:
- `↪` invoke | `🚫` prohibited | `✓` allowed
- `→` delegates | `⚡` fast-path | `🔄` iterate | `⛔` violation

**Scope**: MANDATORY for macros/evidence/invocations | PROHIBITED for prose/explanations
