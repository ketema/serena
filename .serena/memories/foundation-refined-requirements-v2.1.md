# Multi-Project Foundation: Refined Requirements (v2.1)

**Date**: 2026-01-12
**Status**: APPROVED - Incorporating AI Panel (Claude/OpenAI/Gemini) Feedback
**Conversations**: bb33a8d1-69c4-4a8b-be15-974f3fe58ae4, 8e37352e-47a4-4f94-a8c7-38aa8dc9688e

## 1. Thread-Safety (DCL) Requirements

The current "Double-Checked Locking" (DCL) pattern in `mcp.py` is rejected by the AI Panel as non-portable and potentially unsafe for Python's memory model (visibility of partially-constructed objects).

### REQ-DCL-FIX: Safe Singleton Access
**WHAT**: Replace DCL with simple, lock-guarded lazy initialization or module-level initialization.
**WHY**: DCL without `volatile` (unavailable in Python) can leak partially initialized references to other threads.
**EXPECTED**: 
- `get_session_registry()` and others must use a single `with self._lock:` block for the entire check-and-create sequence.
- Performance penalty is negligible for startup singletons.

---

## 2. Security (SEC-5) Requirements

Hashing the `session_id` in `ClangdAdapter` is a good start, but insufficient for "Defense in Depth."

### REQ-SEC-SANITY: Path Traversal Defense
**WHAT**: Implement a three-layer defense for `get_launch_arguments`.
1. **Validation**: session_id must match `^[a-zA-Z0-9\-_]+$`.
2. **Hashing**: Hash the ID to eliminate path interpretation.
3. **Verification**: Call `.resolve()` on the final cache path and verify it is a child of the intended base directory (`/tmp` or `.cache`).
**WHY**: Prevent malicious clients from using session IDs to manipulate the filesystem outside the cache directory.

### REQ-SEC-UNICODE: Unicode Normalization Defense
**WHAT**: Add adversarial tests for Unicode characters that normalize to path separators.
**INPUTS**: U+2044 (FRACTION SLASH), U+FF0F (FULLWIDTH SOLIDUS).
**EXPECTED**: Regex validation must reject these characters before hashing.

---

## 3. LSP Factory (REQ-7) Requirements

The "stub" refactor in `global_lsp_pool.py` is incomplete and dangerously silent.

### REQ-FACTORY-ROBUST: Configuration Fidelity
**WHAT**: Ensure `GlobalLanguageServerPool._create_lsp` injects ALL relevant `project.yml` settings.
**WHY**: Bypassing settings like `trace_lsp_communication` or language-specific overrides breaks user expectations.
**EXPECTED**:
- Load `ProjectConfig`.
- Map relevant fields to `LanguageServerConfig`.
- Support language-specific settings from the project file.

### REQ-ERR-1: Auditable Error Handling
**WHAT**: Remove generic `except Exception: pass` blocks in `_create_lsp`.
**WHY**: Silent failure turns configuration errors into "ghost bugs" where defaults are used without warning.
**EXPECTED**:
- Catch `FileNotFoundError`: Use defaults (log INFO).
- Catch `ValueError` (Validation): Raise or log ERROR + fallback.
- Other Exceptions: Propagate (crash) or log CRITICAL + fallback.

---

## 4. Contract Alignment Requirements

### REQ-CONTRACT-SYNC: Explicit Sanitization Contract
**WHAT**: Update `LSPCapabilityAdapterContract` docstrings.
**WHY**: The contract currently implies raw usage of `session_id`. Implementation hashes it. This divergence breaks Design-by-Contract guarantees.
**EXPECTED**:
- Docstring for `get_launch_arguments` must explicitly state: "Implementation MUST sanitize or hash session_id to prevent path traversal."

---

## 5. Test Requirements (MANDATORY)

### REQ-TEST-CONCURRENCY
**WHAT**: Add a test that uses a `threading.Barrier` to force 10 threads to initialize the `SerenaMCPFactory` singletons simultaneously.
**WHY**: Prove the fix for CRIT-1 actually works under load.

### REQ-TEST-SEC-5-DEEP
**WHAT**: Add tests for:
- Null byte injection (`\x00`).
- Absolute path session IDs.
- URL-encoded traversal (`%2F`).
- Unicode normalization vectors (REQ-SEC-UNICODE).
**WHY**: Ensure the sanitization in REQ-SEC-SANITY handles common injection vectors.