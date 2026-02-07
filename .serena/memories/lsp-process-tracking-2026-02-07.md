# LSP Process Tracking — 2026-02-07

## Purpose
Profile LSP usage across projects. Track process lifecycle: spawn, kill, restart.
Future: compare against pool state to verify graceful shutdown wiring works in production.

## Baseline Snapshot (2026-02-07 17:56 EST)

### Active (Fresh — Post-Restart)
| PID | PPID | Spawned | Language | Project | Parent Process |
|-----|------|---------|----------|---------|----------------|
| 73668 | 66431 | 17:56 EST | pyright (Python wrapper) | serena | Serena MCP (com.ketema.serena-mcp-test) |
| 73670 | 73668 | 17:56 EST | pyright (node langserver) | serena | Child of 73668 |

Serena PID: 66431 (started ~17:24 EST via `launchctl kickstart -k`)

### Killed (Orphaned Zombies — Pre-Shutdown-Wiring)
| PID | PPID | Age at Kill | Language | Likely Origin |
|-----|------|-------------|----------|---------------|
| 4655 | 4608 | 15h 30m | pyright | Old Serena instance (pre-restart, no shutdown handler) |
| 4701 | 4655 | 15h 30m | pyright node | Child of 4655 |
| 11964 | 11918 | 3h 20m | pyright | Old Serena instance |
| 12011 | 11964 | 3h 20m | pyright node | Child of 11964 |
| 41424 | 41386 | 8h 44m | pyright | Old Serena instance |
| 41472 | 41424 | 8h 44m | pyright node | Child of 41424 |
| 41657 | 41618 | 8h 44m | pyright | Old Serena instance |
| 41700 | 41657 | 8h 44m | pyright node | Child of 41657 |

**Total killed**: 8 processes (4 pyright pairs)
**Reason orphaned**: No SIGTERM handler existed before commit 50b2f977 (REQ-GRACEFUL-SHUTDOWN-001)

## Tracking Protocol

On future restarts, record:
1. Pre-restart LSP PIDs (should be killed by graceful shutdown)
2. Post-restart LSP PIDs (fresh, spawned by new Serena instance)
3. Any orphans found (indicates shutdown wiring failure)
4. Project associated with each LSP (from pool state or workspace root)

## Cross-Project Usage Pattern (To Be Populated)
| Date | Project | Language | LSP Type | Duration | Trigger |
|------|---------|----------|----------|----------|---------|
| 2026-02-07 | serena | Python | pyright | active | activate_project via MCP client |
