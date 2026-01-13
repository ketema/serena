"""
Issue #6 Constants - Design Decisions

Constitutional Reference: CL12 Design by Contract
Domain: Configuration constants for multi-project session isolation
Version: 1.0
"""

# Session cleanup constants
SESSION_DEFAULT_TTL_SECONDS = 3600  # 1 hour default TTL
SESSION_ANONYMOUS_TTL_SECONDS = 300  # 5 minutes for anonymous sessions
SESSION_REAPER_INTERVAL_SECONDS = 60  # Check for expired sessions every minute
SESSION_MAX_IDLE_SECONDS = 1800  # 30 minutes max idle before eligible for cleanup

# Observable enforcement thresholds (INV-5 caller responsibility verification)
TOUCH_STALENESS_THRESHOLD_SECONDS = 1  # If last_activity_time older than this after tool call, caller violated contract

# LSP pool constants
LSP_IDLE_TIMEOUT_SECONDS = 3600  # 1 hour idle before reclamation
LSP_MAX_WORKSPACES_PER_INSTANCE = 50  # Limit per multi-root LSP (CON-3 memory)
