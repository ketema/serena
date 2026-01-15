# Upstream PR: MCP Protocol Version Comma Parsing

**Status**: SUBMITTED - Issue #1861 created, local patch committed (e55769c0)
**Priority**: HIGH (affects all MCP clients that send multiple versions)

## Target Repository

- **Package**: `mcp` (Model Context Protocol Python SDK)
- **Repository**: https://github.com/modelcontextprotocol/python-sdk
- **Version with bug**: 1.25.0
- **Maintainers**: Anthropic, PBC (David Soria Parra, Justin Spahr-Summers)

## Bug Description

`StreamableHTTPServerTransport._validate_protocol_version()` in `mcp/server/streamable_http.py` 
does NOT parse comma-separated protocol version headers.

**Current behavior** (WRONG):
```python
protocol_version = request.headers.get(MCP_PROTOCOL_VERSION_HEADER)
if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
    # "2025-11-25, 2025-06-18" is NOT in ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]
    # Returns 400 Bad Request
```

**Expected behavior** (FIX):
```python
# Parse comma-separated versions
versions = [v.strip() for v in protocol_version.split(',')]
# Sort by date descending (newest first)
versions.sort(reverse=True)
# Return newest mutually supported version
for version in versions:
    if version in SUPPORTED_PROTOCOL_VERSIONS:
        return True  # Valid
return False  # No match
```

## Affected Clients

- Claude Code (sends "2025-11-25, 2025-06-18" after negotiation)
- Gemini (observed same pattern in AI Panel work)
- Any MCP client that follows spec for multi-version negotiation

## Evidence

- Commit `72340329` in ametek_chess AI Panel fixed identical bug in Rust
- ngrep capture shows Claude Code sending comma-separated header
- MCP Spec 2025-03-26 allows comma-separated version negotiation

## PR Template (Draft)

**Title**: fix(server): Parse comma-separated protocol version headers

**Body**:
```
## Summary
Fix protocol version validation to parse comma-separated headers per MCP spec.

## Problem
Clients like Claude Code and Gemini send multiple protocol versions in the 
`mcp-protocol-version` header (e.g., "2025-11-25, 2025-06-18"). The current 
implementation treats this as a single string, causing 400 Bad Request even 
when a supported version is present.

## Solution
- Parse all versions from comma-separated header
- Sort by date descending (newest first)
- Return first mutually supported version

## Testing
- [ ] Unit tests for comma-separated parsing
- [ ] Integration test with Claude Code client
- [ ] Backward compatibility with single-version headers
```

## Local Fix Reference

See Serena patch in `src/serena/patches/mcp/server/` for working implementation.
