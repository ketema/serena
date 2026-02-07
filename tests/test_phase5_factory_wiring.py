"""
CL12 Tier 1.5 Integration Tests for SEQ-POOL-05 Factory Wiring (REQ-2026-005 Phase 5).

Contract Authority: contracts/lsp_lifecycle_authority_contract.py

This file tests the production wiring obligation:
    SEQ-POOL-05-FACTORY: SerenaMCPFactory.get_session_bridge() MUST pass
                         factory.get_lsp_pool() to MCPSessionBridge constructor.

Failure mode: If factory doesn't pass lsp_pool reference, MCPSessionBridge._lsp_pool
              remains None, causing SEQ-POOL-05 cleanup chain to be dead code.

Test Tier: 1.5 (Integration Wiring)
    - Tests WHO calls WHOM with WHAT parameters
    - Verifies that singletons are wired together at construction time
    - Uses actual construction paths (lazy factory methods)
    - Validates object identity (same instance, not just equal values)

Test Discipline:
    - Constructs bridge through factory.get_session_bridge() (actual lifecycle path)
    - Verifies wiring through bridge's internal state (_lsp_pool attribute)
    - Does NOT test bridge or pool behavior (those are separate contracts)
    - Does NOT directly construct MCPSessionBridge (tests through factory)
"""

import pytest

from serena.global_lsp_pool import GlobalLanguageServerPool
from serena.mcp import SerenaMCPFactory
from serena.mcp_session_bridge import MCPSessionBridge


class TestFactoryWiring:
    """
    Test suite for SEQ-POOL-05-FACTORY production wiring.

    Enforces: Factory MUST wire GlobalLanguageServerPool reference into
              MCPSessionBridge at construction time.
    """

    def test_seq_pool_05_factory_wiring_positive(self) -> None:
        """
        CONTRACT TRACEABILITY:
        - Contract: SerenaMCPFactory.get_session_bridge()
        - Enforces: SEQ-POOL-05-FACTORY (production wiring obligation)
        - Category: positive (wiring success)
        - Adversarial: Implementation-blind

        BEHAVIORAL REQUIREMENT:
        When factory creates bridge singleton, bridge._lsp_pool MUST be:
        1. Non-None (wiring occurred)
        2. The same object as factory.get_lsp_pool() (correct reference)

        SEQ TEST SELF-CHECK:
        [✓] Constructs parent (factory) via __init__()
        [✓] Verifies through parent state (bridge._lsp_pool)
        [✓] Does NOT directly call callee (MCPSessionBridge constructor)
        [✓] No mocks — uses actual factory lifecycle
        """
        # ARRANGE: Create factory (no real project needed for singleton access)
        factory = SerenaMCPFactory(context="agent", project=None)

        # ACT: Invoke factory lifecycle to create singletons
        bridge = factory.get_session_bridge()
        pool = factory.get_lsp_pool()

        # ASSERT: SEQ-POOL-05-FACTORY - bridge MUST have pool reference
        # Requirement 1: Bridge has non-None lsp_pool
        assert bridge._lsp_pool is not None, (
            f"SEQ-POOL-05-FACTORY violation: MCPSessionBridge._lsp_pool is None\n"
            f"Contract: SerenaMCPFactory.get_session_bridge() SEQ-POOL-05-FACTORY\n"
            f"EXPECTED: factory.get_session_bridge() passes factory.get_lsp_pool() to bridge constructor\n"
            f"ACTUAL: bridge._lsp_pool is None (factory did not pass lsp_pool parameter)\n"
            f"FAILURE MODE: SEQ-POOL-05 cleanup chain (on_transport_session_closed → pool.release) is dead code\n"
            f"GUIDANCE: When constructing MCPSessionBridge singleton, factory MUST pass lsp_pool reference. "
            f"The bridge constructor already accepts lsp_pool parameter. Factory must call: "
            f"MCPSessionBridge(session_registry, lsp_pool=self.get_lsp_pool()). "
            f"This wiring is critical for session cleanup — without pool reference, disconnected sessions "
            f"never release LSP references, causing ref count leaks."
        )

        # ASSERT: SEQ-POOL-05-FACTORY - bridge pool MUST be same instance as factory pool
        # Requirement 2: Identity check (same object, not just equal)
        assert bridge._lsp_pool is pool, (
            f"SEQ-POOL-05-FACTORY violation: bridge._lsp_pool is not the same object as factory.get_lsp_pool()\n"
            f"Contract: SerenaMCPFactory.get_session_bridge() SEQ-POOL-05-FACTORY\n"
            f"EXPECTED: bridge._lsp_pool is factory.get_lsp_pool() (identity: both variables reference SAME singleton)\n"
            f"ACTUAL: bridge._lsp_pool is {bridge._lsp_pool}, factory.get_lsp_pool() is {pool} (different objects)\n"
            f"FAILURE MODE: Multiple GlobalLanguageServerPool instances exist, violating singleton pattern. "
            f"Session cleanup calls release() on WRONG pool instance.\n"
            f"GUIDANCE: Factory singleton methods (get_lsp_pool, get_session_bridge) MUST use same factory instance. "
            f"Both singletons must be created from same factory._lock context. Do NOT create separate pools. "
            f"The bridge must receive THE SAME pool object that factory.get_lsp_pool() returns."
        )

    def test_seq_pool_05_factory_singleton_lifecycle(self) -> None:
        """
        CONTRACT TRACEABILITY:
        - Contract: SerenaMCPFactory singleton lifecycle
        - Enforces: SEQ-POOL-05-FACTORY (multiple calls return same wiring)
        - Category: positive (idempotency)
        - Adversarial: Implementation-blind

        BEHAVIORAL REQUIREMENT:
        Multiple calls to get_session_bridge()/get_lsp_pool() MUST return
        same instances with stable wiring (idempotent singleton access).

        SEQ TEST SELF-CHECK:
        [✓] Constructs parent (factory) via __init__()
        [✓] Verifies through parent state (singleton identity)
        [✓] Does NOT directly call callee
        [✓] No mocks — tests actual factory lifecycle
        """
        # ARRANGE: Create factory
        factory = SerenaMCPFactory(context="agent", project=None)

        # ACT: Call factory methods multiple times
        bridge1 = factory.get_session_bridge()
        bridge2 = factory.get_session_bridge()
        pool1 = factory.get_lsp_pool()
        pool2 = factory.get_lsp_pool()

        # ASSERT: Same singleton instances returned
        assert bridge1 is bridge2, (
            f"Factory singleton violation: get_session_bridge() returned different instances\n"
            f"EXPECTED: bridge1 is bridge2 (same object)\n"
            f"ACTUAL: bridge1={id(bridge1)}, bridge2={id(bridge2)} (different objects)\n"
            f"GUIDANCE: Factory lazy singleton pattern MUST ensure only ONE MCPSessionBridge instance exists. "
            f"Check factory._lock usage and None-check before construction."
        )

        assert pool1 is pool2, (
            f"Factory singleton violation: get_lsp_pool() returned different instances\n"
            f"EXPECTED: pool1 is pool2 (same object)\n"
            f"ACTUAL: pool1={id(pool1)}, pool2={id(pool2)} (different objects)\n"
            f"GUIDANCE: Factory lazy singleton pattern MUST ensure only ONE GlobalLanguageServerPool instance exists. "
            f"Check factory._lock usage and None-check before construction."
        )

        # ASSERT: Wiring stable across calls
        assert bridge1._lsp_pool is pool1, (
            f"SEQ-POOL-05-FACTORY wiring unstable: bridge._lsp_pool changed across factory calls\n"
            f"EXPECTED: bridge1._lsp_pool is pool1 (wiring preserved)\n"
            f"ACTUAL: bridge1._lsp_pool={id(bridge1._lsp_pool)}, pool1={id(pool1)}\n"
            f"GUIDANCE: Wiring established during bridge construction MUST be immutable. "
            f"Do NOT replace bridge._lsp_pool after construction."
        )
