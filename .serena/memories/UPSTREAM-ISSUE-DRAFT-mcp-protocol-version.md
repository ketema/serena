# Discussion: Where should MCP protocol version negotiation happen?

## Status
**READY FOR REVIEW** - Reframed as discussion after adversarial analysis

## Key Insight
This may NOT be a bug. The spec uses singular form for protocol version header.
Three major clients (Claude, Codex, Gemini) send comma-separated, but spec says "the ONE negotiated."

## Core Question
WHERE is protocol version negotiation supposed to happen?
- Interpretation A: HTTP header (like Accept-Language content negotiation)
- Interpretation B: JSON body during initialize (header is AFTER negotiation)

## Draft Location
/tmp/mcp-upstream-issue-draft.md

## Action Items
- [ ] User reviews updated draft
- [ ] Decide: Post as discussion to elicit maintainer perspective
- [ ] Still patch Serena locally for defensive interoperability