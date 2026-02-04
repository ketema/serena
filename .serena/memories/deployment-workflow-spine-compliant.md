# SPINE-Compliant Deployment Workflow

**Last Updated**: 2026-01-11
**Status**: Active
**Authoritative Contract**: `REQ-2026-001-deployment-cross-reference.md`

## Architecture Overview

Three-plane separation ensures no single identity can author + approve + execute:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WORKSTATION (dev repo)                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Claude + User create dev issue (interactive session)         │   │
│  │    └─ Payload: commit SHA, image digest, nonce, timestamp       │   │
│  │ 2. Mac signs dev issue (Touch ID → Secure Enclave)              │   │
│  │    └─ Comment: MAC-P256-SIGNATURE                               │   │
│  │ 3. Label: deployment-pending                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  iPHONE (Deploy Guard App)                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 4. Face ID authentication                                       │   │
│  │ 5. Fetch pending dev issues, verify MAC signature               │   │
│  │ 6. iPhone signs DEV ISSUE (adds IPHONE-P256-SIGNATURE comment)  │   │
│  │    └─ Dev issue now has BOTH signatures                         │   │
│  │ 7. Label: deployment-signed                                     │   │
│  │ 8. Create PRODUCTION ISSUE with:                                │   │
│  │    └─ Dev Issue: #N (cross-reference)                           │   │
│  │    └─ IPHONE-P256-SIGNATURE only                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PRODUCTION (${PRODUCTION_REPO} - user-provided variable in app)        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 9.  Production issue triggers GitHub Actions workflow           │   │
│  │ 10. Validator fetches dev issue #N from KNOWN dev repo          │   │
│  │ 11. Validator verifies MAC-P256-SIGNATURE on dev issue          │   │
│  │ 12. Validator verifies IPHONE-P256-SIGNATURE on dev issue       │   │
│  │ 13. Validator confirms payload integrity (commit, image, nonce) │   │
│  │ 14. Deploy to target environment                                │   │
│  │ 15. On success: Close BOTH issues with artifact SHA attestation │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Important Design Decisions

### Production Repo is User-Provided
The production repository name is NOT hardcoded. The user enters it as a variable in the Deploy Guard iOS app. This is intentional SPINE design for flexibility.

### Dev Repo is FIXED
The dev repo identity is HARDCODED in the production validator. This is a security boundary - prevents redirect attacks.

### Labels are NOT Security Boundaries
Labels (`deployment-pending`, `deployment-signed`, etc.) are workflow convenience. The SIGNATURES are the actual authorization - Secure Enclave + biometric.

## Hard Invariants (INV-01 through INV-08)

| ID | Invariant |
|----|-----------|
| INV-01 | At most ONE deployment issue may have `deployment-pending` label at any time |
| INV-02 | Reopened deployment issues IMMEDIATELY closed and marked invalid |
| INV-03 | Labels do NOT authorize deployment; only valid signatures do |
| INV-04 | Dev repo identity FIXED in validator; never parsed from input |
| INV-05 | Dev issue MUST contain BOTH MAC-P256-SIGNATURE and IPHONE-P256-SIGNATURE before production issue created |
| INV-06 | Each deployment has unique nonce; replay of old nonce rejected |
| INV-07 | Deployment pending >24h without iPhone signature automatically expires |
| INV-08 | Successful deployment closes BOTH prod and dev issues with matching attestation (artifact SHA) |

## Issue Formats

### Dev Issue Format
```markdown
## Deployment Request

**Issue ID:** DEPLOY-XXX
**Timestamp:** 2026-01-10T00:52:54Z
**Commit SHA:** abc123def456789...
**Image Digest:** sha256:...
**Nonce:** 550e8400-e29b-41d4-a716-446655440000

## Comments:
- MAC-P256-SIGNATURE: cd8afba051cd...      ← Mac signs first
- IPHONE-P256-SIGNATURE: MEYCIQCmSZIs...   ← iPhone signs second
```

### Production Issue Format
```markdown
## Deployment Approved

**Dev Issue:** #N
**IPHONE-P256-SIGNATURE:** MEYCIQCmSZIs...
```

### Closure Attestation (Both Issues)
```markdown
## Deployment Complete

**Artifact SHA:** sha256:...
**Deployed At:** 2026-01-10T01:15:00Z
```

## Key Files

| File | Purpose |
|------|---------|
| `rust/mcp_workspace/deployment/scripts/approve-deploy.sh` | Mac Touch ID signing |
| `ios/deploy_guard/Sources/DeployGuard/GitHub/DeploymentIssue.swift` | Domain model |
| `ios/deploy_guard/Sources/DeployGuard/GitHub/GitHubClient.swift` | GitHub API |
| `ios/deploy_guard/DeployGuardApp/DeployGuardApp/Views/SigningView.swift` | iPhone signing UI |
| `ios/deploy_guard/Sources/DeployGuard/GitHub/GitHubAPIContract.swift` | Issue format validators |
| `.github/workflows/deployment-label-enforcement.yml` | Label state machine (dev repo) |

## Cryptographic Details

**Mac Signing**:
- Algorithm: ECDSA P-256
- Key Storage: Secure Enclave
- Authentication: Touch ID
- Tool: `deploy-signer` binary

**iPhone Signing**:
- Algorithm: ECDSA P-256
- Key Storage: Secure Enclave (kSecAttrTokenIDSecureEnclave)
- Authentication: Face ID (LAContext)
- Key Tag: `com.ketema.deployguard.signing`

**Commit Signing**:
- Algorithm: GPG (RSA/EdDSA)
- Attestation: OpenTimestamps (Bitcoin blockchain merkle roots)
- Verification: `git log --show-signature`

## Implementation Gaps (Phase 4 Work)

| Gap | Impact | Fix Required |
|-----|--------|--------------|
| Commit SHA missing from dev issue | Can't pin deployment to specific code | Add `commitSha` to payload + format |
| No dev issue cross-reference in prod | Traceability gap | Add `Dev Issue: #N` field |
| No label enforcement workflow | Queue spam possible | Create GitHub Actions workflow |
| No closure attestation | Audit trail incomplete | Add artifact SHA on both issues |
| DeploymentIssue.swift missing field | iOS can't display/sign SHA | Add `commitSha` property |
