# REQ-2026-001: SPINE-Compliant Deployment Cross-Reference

## 1. Intent Traceability

- **Source Prose**:
  > "I will need brainstorming on this we need something that cannot be spoofed. if a redirect is tried we need to be able to detect it.
  >
  > we know the dev repo so we will always be checking there. issue number would seem to be the simplest solution and I can't think of any reason it wouldn't work. it is guaranteed unique, and the content is what we verify."
  >
  > "it is minor but I want to be clear about the iPhone Approves step. The way it works NOW is that the iPhone approves by signing the dev issue FIRST (so it winds up with two signatures) and then creates the prod deployment issue with its signature alone."
  >
  > "when the prod deployment finishes it will mark its own prod issue as closed with an attestation of some sort (artifact build sha?) as well as the originating dev issue/pr with that same attestation"

- **Our Understanding**: Dev issue number serves as tamper-evident cross-reference. Production validator fetches from KNOWN dev repo (not user input), verifying both signatures on dev issue. Successful deployment closes both issues with matching artifact attestation.

- **Ambiguity Score**: 2 (Ready for contracts)

## 2. The Actor Matrix

| Actor | Permission Level | Prohibited Actions |
|:------|:-----------------|:-------------------|
| Claude + User | Create dev issue, define payload | Cannot sign |
| Mac (Secure Enclave) | Sign dev issue payload (Touch ID) | Cannot create issues, cannot sign without biometric |
| iPhone (Secure Enclave) | Sign dev issue, create prod issue (Face ID) | Cannot sign without biometric, cannot skip Mac verification |
| GitHub Actions (Dev) | Enforce label state machine, auto-close violations | Cannot sign, cannot deploy |
| GitHub Actions (Prod) | Validate signatures, deploy, close issues | Cannot sign, cannot bypass signature verification |
| Attacker | None | Cannot forge signatures, cannot redirect validator to wrong repo |

## 3. The State Transition

### Dev Issue Lifecycle
- **Initial State ($S_0$)**: Issue created with `deployment-pending` label, payload (commit SHA, image digest, nonce, timestamp)
- **Transformation T1**: Mac signs → MAC-P256-SIGNATURE comment added
- **Transformation T2**: iPhone verifies + signs → IPHONE-P256-SIGNATURE comment added, label → `deployment-signed`
- **Transformation T3**: Production deploys → issue closed with artifact SHA attestation
- **Terminal State ($S_1$)**: Issue closed, contains both signatures + deployment attestation

### Production Issue Lifecycle
- **Initial State ($S_0$)**: Issue created by iPhone with dev issue cross-reference + IPHONE-P256-SIGNATURE
- **Transformation**: GitHub Actions validates → deploys → closes with attestation
- **Terminal State ($S_1$)**: Issue closed with artifact SHA attestation matching dev issue

## 4. Hard Invariants (The "Never" List)

| ID | Category | Invariant |
|----|----------|-----------|
| INV-01 | Queue | At most ONE deployment issue may have `deployment-pending` label at any time |
| INV-02 | Reopen | Reopened deployment issues IMMEDIATELY closed and marked invalid |
| INV-03 | Authority | Labels do NOT authorize deployment; only valid signatures do |
| INV-04 | Dev Repo | Dev repo identity FIXED in validator; never parsed from input |
| INV-05 | Signatures | Dev issue MUST contain BOTH MAC-P256-SIGNATURE and IPHONE-P256-SIGNATURE before production issue created |
| INV-06 | Nonce | Each deployment has unique nonce; replay of old nonce rejected |
| INV-07 | Expiry | Deployment pending >24h without iPhone signature automatically expires |
| INV-08 | Closure | Successful deployment closes BOTH prod and dev issues with matching attestation (artifact SHA) |

## 5. High-Entropy Zones (Adjudicated)

| Zone | Question | Resolution | Decided By |
|------|----------|------------|------------|
| Cross-reference format | URL vs issue number? | Issue number (simpler, unique, content verified via fetch) | User |
| Dev repo identity | Configurable or fixed? | FIXED in validator (security boundary) | User |
| Production repo identity | Configurable or fixed? | User-provided variable in app (flexibility) | User |
| Queue control | Independent or sequential? | Sequential - one pending at a time | User |
| Reopen handling | Allow or block? | Block - auto-close reopened issues | User |
| Expiry window | Time-based? | Yes - 24h without signature = auto-expire | User |
| Signature location | Both on prod issue? | No - both on DEV issue, prod has iPhone only + cross-ref | User |
| Closure attestation | What artifact? | Artifact build SHA on BOTH issues | User |

## 5.5 Rejected Alternatives

| Decision | Alternative Considered | Why Rejected |
|----------|----------------------|--------------|
| Issue number cross-ref | Full URL cross-ref | URL could be spoofed/redirected; issue # + KNOWN repo is tamper-evident |
| Sequential deployments | Independent deployments | Queue spam attack vector; biometric still required but annoying |
| Auto-close on reopen | Allow reopen with re-sign | Complexity; signatures tied to original timeline/nonce |
| 24h expiry | No expiry | Stale deployments could block queue indefinitely |
| Both sigs on dev issue | Both sigs on prod issue | Current architecture; prod issue is trigger, dev issue is source of truth |

## 6. Tool/API Interface Summary

| Interface | Purpose | Mutates State? |
|-----------|---------|----------------|
| `approve-deploy.sh` | Mac Touch ID signing of dev issue | YES (adds comment) |
| Deploy Guard iOS App | iPhone signing + prod issue creation | YES (adds comment, creates issue) |
| GitHub Actions (Dev) | Label enforcement, expiry, auto-close | YES (labels, closes) |
| GitHub Actions (Prod) | Signature validation, deployment, attestation | YES (deploys, closes both issues) |
| `deploy-signer` | Secure Enclave P256 signing | NO (pure function) |

## 6.5 Blocking Dependencies

| Unresolved Zone | Blocks |
|-----------------|--------|
| None | All zones adjudicated |

## 7. Completion Promise (Ralph Loop Exit)

> **A deployment CANNOT reach production unless:**
> 1. Exactly ONE dev issue exists with `deployment-pending` → `deployment-signed` state
> 2. Dev issue contains payload: commit SHA, image digest, nonce, timestamp
> 3. Dev issue contains valid MAC-P256-SIGNATURE (Mac Secure Enclave, Touch ID)
> 4. Dev issue contains valid IPHONE-P256-SIGNATURE (iPhone Secure Enclave, Face ID)
> 5. Production issue exists referencing dev issue number
> 6. Production issue contains IPHONE-P256-SIGNATURE
> 7. Validator fetches dev issue from KNOWN dev repo (hardcoded, not parsed)
> 8. Validator verifies BOTH signatures on dev issue
> 9. Timestamp within 24h window
> 10. Nonce never used before
> 11. On success: BOTH issues closed with matching artifact SHA attestation

### Adversarial Verification Tests

| Test | Invariant | Expected Result |
|------|-----------|-----------------|
| Create 2nd deployment while 1st pending | INV-01 | Auto-close with "previous pending" message |
| Reopen closed deployment | INV-02 | Auto-close with "reopened invalid" message |
| Apply `deployment-signed` label manually | INV-03 | Deployment fails (no valid signatures) |
| Forge prod issue pointing to wrong dev# | INV-04 | Validation fails (fetches from KNOWN repo) |
| Create prod issue before iPhone signs dev | INV-05 | Validation fails (missing IPHONE sig on dev) |
| Replay old deployment with same nonce | INV-06 | Rejected (nonce already used) |
| Leave deployment unsigned >24h | INV-07 | Auto-expire and close |
| Deployment succeeds but only prod closed | INV-08 | Violation (both must close with attestation) |

## 8. Contract Authority

**Authoritative Source**: This manifest

```
REQ-2026-001-deployment-cross-reference.md (this file)
        ↓
contracts/deployment_cross_reference_contract.py (CL12 contract)
        ↓
tests/test_deployment_cross_reference_contract.py (verification)
        ↓
Implementation across:
  - ios/deploy_guard/ (DeploymentIssue.swift, SigningView.swift)
  - rust/mcp_workspace/deployment/scripts/approve-deploy.sh
  - .github/workflows/ (label enforcement - dev repo)
  - ${PRODUCTION_REPO}/.github/workflows/ (validation - separate machine)
```

## 9. Revision History

| Date | Author | Change |
|------|--------|--------|
| 2026-01-11 | User + Claude | Initial manifest from req-elicit |
