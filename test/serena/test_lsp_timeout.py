"""
Tests for LSPTimeoutManager - manages per-language idle timeouts for LSP reclamation.

Following adversarial TDD approach: Tests written FIRST before implementation.
Contract: contracts/lsp_timeout_contract.py (verified: 2026-01-11)
Issue: REQ-4 - LSP lifecycle management with idle timeouts

STRUCTURAL BLINDNESS: This test suite is written without access to implementation code.
All error messages must be self-documenting for the coder agent.
"""

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from freezegun import freeze_time

from contracts.lsp_timeout_contract import (
    DEFAULT_TIMEOUTS_SECONDS,
    RECLAIM_TEST_CASES,
    TIMEOUT_TEST_CASES,
    verify_timeout_defaults,
)


class TestLSPTimeoutManagerContract:
    """Test LSPTimeoutManager behavioral contract adherence."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_contract_timeout_defaults_valid(self):
        """
        Test that contract default timeouts are valid configuration.

        CONTRACT VERIFICATION:
        - INV-1: All timeout values are positive integers (seconds)
        - Contract defines DEFAULT_TIMEOUTS_SECONDS with proper values

        WHAT: Contract helper verify_timeout_defaults() validation
        WHY: Ensures contract test data integrity before mock derivation
        EXPECTED: verify_timeout_defaults() returns True
        ACTUAL: Returns {result}
        GUIDANCE: Contract must define valid timeout configuration with:
            - All values as positive integers
            - "default" key present in configuration
            - No negative or zero timeout values
        """
        result = verify_timeout_defaults()
        assert result is True, (
            f"❌ CONTRACT VIOLATION: Default timeout configuration is invalid\n"
            f"WHAT FAILED: verify_timeout_defaults() returned {result}\n"
            f"WHY: Contract test data must be valid for mock derivation (CL10)\n"
            f"EXPECTED: All timeouts > 0, 'default' key present\n"
            f"ACTUAL: Validation failed - check DEFAULT_TIMEOUTS_SECONDS in contract\n"
            f"GUIDANCE: Fix contract configuration to satisfy INV-1:\n"
            f"  - All timeout values must be positive integers\n"
            f"  - 'default' key must be present\n"
            f"  - Typical values: 1800 (30min), 3600 (1hr)"
        )


class TestLSPTimeoutManagerInitialization:
    """Test LSPTimeoutManager initialization and configuration."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_implementation_imports_contract_defaults(self):
        """
        Test that implementation imports DEFAULT_TIMEOUTS_SECONDS from contract (not hardcoded).

        CONTRACT: CL10 Mock Verification
        - Implementation must import contract constants, not invent values
        - Prevents divergence between contract and implementation

        WHAT: Verify DEFAULT_TIMEOUTS_SECONDS imported in lsp_timeout module
        WHY: CL10 requires contract-driven configuration (not hardcoded values)
        EXPECTED: DEFAULT_TIMEOUTS_SECONDS imported from contract in implementation
        ACTUAL: Import {found_or_not}
        GUIDANCE: Implementation must import contract defaults:
            from contracts.lsp_timeout_contract import DEFAULT_TIMEOUTS_SECONDS
            - Do NOT copy values into implementation
            - Do NOT hardcode timeout values
            - Use contract as single source of truth
        """
        try:
            from serena.lsp_timeout import LSPTimeoutManager
        except ImportError:
            pytest.skip("Implementation module does not exist yet")

        # Read implementation source to verify import
        import inspect
        source = inspect.getsource(LSPTimeoutManager.__module__)

        has_contract_import = "from contracts.lsp_timeout_contract import" in source and "DEFAULT_TIMEOUTS_SECONDS" in source

        assert has_contract_import, (
            "❌ CONTRACT VIOLATION (CL10): Implementation does not import contract defaults\n"
            "WHAT FAILED: Contract import verification in lsp_timeout.py\n"
            "WHY: CL10 requires mocks/configs to derive from verified contracts\n"
            "EXPECTED: Line like 'from contracts.lsp_timeout_contract import DEFAULT_TIMEOUTS_SECONDS'\n"
            "ACTUAL: Import not found in implementation source\n"
            "GUIDANCE: Add contract import at top of lsp_timeout.py:\n"
            "  from contracts.lsp_timeout_contract import DEFAULT_TIMEOUTS_SECONDS\n"
            "  Then use: timeout_config = timeout_config or DEFAULT_TIMEOUTS_SECONDS\n"
            "  Do NOT hardcode values - contract is single source of truth"
        )

    def test_initialization_with_default_timeouts(self):
        """
        Test LSPTimeoutManager initialization uses contract default timeouts.

        WHAT: LSPTimeoutManager() initialization with no custom config
        WHY: REQ-4 requires per-language configurable timeouts with sensible defaults
        EXPECTED: Instance created with DEFAULT_TIMEOUTS_SECONDS from contract
        ACTUAL: {type(timeout_manager).__name__} instance with config {config}
        GUIDANCE: Constructor must accept optional timeout_config parameter:
            - If None, load DEFAULT_TIMEOUTS_SECONDS from contract
            - Store configuration for later get_timeout() queries
            - Do NOT hardcode values - import from contract
        """
        # Import will be added by coder
        # from serena.lsp_timeout import LSPTimeoutManager

        # This import will fail initially - coder will create the module
        try:
            from serena.lsp_timeout import LSPTimeoutManager
        except ImportError as e:
            pytest.fail(
                f"❌ MODULE NOT FOUND: serena.lsp_timeout module does not exist\n"
                f"WHAT FAILED: import LSPTimeoutManager from serena.lsp_timeout\n"
                f"WHY: REQ-4 requires LSPTimeoutManager component for idle timeout management\n"
                f"EXPECTED: Module at src/serena/lsp_timeout.py with LSPTimeoutManager class\n"
                f"ACTUAL: ImportError: {e}\n"
                f"GUIDANCE: Create module src/serena/lsp_timeout.py with class:\n"
                f"  class LSPTimeoutManager:\n"
                f"      def __init__(self, timeout_config=None): ...\n"
                f"  Import DEFAULT_TIMEOUTS_SECONDS from contract for defaults"
            )

        timeout_manager = LSPTimeoutManager()

        # Verify rust timeout (heavy LSP)
        rust_timeout = timeout_manager.get_timeout("rust")
        assert rust_timeout == 1800, (
            f"❌ TIMEOUT CONFIG ERROR: Rust timeout does not match contract\n"
            f"WHAT FAILED: get_timeout('rust') returned {rust_timeout}\n"
            f"WHY: Contract specifies rust as heavy LSP with 30min (1800s) timeout\n"
            f"EXPECTED: 1800 seconds (from DEFAULT_TIMEOUTS_SECONDS['rust'])\n"
            f"ACTUAL: {rust_timeout}\n"
            f"GUIDANCE: get_timeout() must return configured value from contract:\n"
            f"  - Import DEFAULT_TIMEOUTS_SECONDS from contract\n"
            f"  - Return timeout_config.get(language, timeout_config['default'])\n"
            f"  - Do NOT hardcode timeout values"
        )

    def test_initialization_with_custom_timeouts(self):
        """
        Test LSPTimeoutManager initialization with custom timeout configuration.

        WHAT: LSPTimeoutManager(timeout_config=custom) initialization
        WHY: REQ-4 requires per-language configurable timeouts (not just defaults)
        EXPECTED: Custom timeout values override defaults
        ACTUAL: get_timeout('python') = {actual_timeout}
        GUIDANCE: Constructor must accept and store custom timeout_config:
            - Accept dict[str, int] parameter for custom timeouts
            - Override defaults with custom values
            - Still fall back to 'default' key for unknown languages
        """
        from serena.lsp_timeout import LSPTimeoutManager

        custom_config = {
            "python": 7200,  # 2 hours (custom)
            "rust": 900,     # 15 min (custom)
            "default": 1800, # 30 min (custom default)
        }

        timeout_manager = LSPTimeoutManager(timeout_config=custom_config)

        python_timeout = timeout_manager.get_timeout("python")
        assert python_timeout == 7200, (
            f"❌ CUSTOM CONFIG ERROR: Custom timeout not applied\n"
            f"WHAT FAILED: get_timeout('python') with custom config\n"
            f"WHY: REQ-4 requires configurable timeouts (not hardcoded defaults)\n"
            f"EXPECTED: 7200 seconds (custom value passed to constructor)\n"
            f"ACTUAL: {python_timeout}\n"
            f"GUIDANCE: Constructor must store and use custom timeout_config:\n"
            f"  - Store timeout_config parameter as instance variable\n"
            f"  - get_timeout() returns config[language] if present\n"
            f"  - Falls back to config['default'] for unknown languages"
        )


class TestLSPTimeoutManagerGetTimeout:
    """Test get_timeout() method per contract POST-2."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @pytest.mark.parametrize("language,expected_timeout,description", TIMEOUT_TEST_CASES)
    def test_get_timeout_contract_cases(self, language, expected_timeout, description):
        """
        Test get_timeout() returns correct values per contract test cases.

        CONTRACT: POST-2 (get_timeout)
        - Returns configured timeout if language in config
        - Returns default timeout if language not in config
        - Always returns int > 0

        WHAT: get_timeout('{language}') call
        WHY: {description}
        EXPECTED: {expected_timeout} seconds (from contract TIMEOUT_TEST_CASES)
        ACTUAL: {actual_timeout}
        GUIDANCE: get_timeout() must implement POST-2 contract:
            - Look up language in timeout_config
            - If found, return timeout_config[language]
            - If NOT found, return timeout_config['default']
            - Never return None, 0, or negative values
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()
        actual_timeout = timeout_manager.get_timeout(language)

        assert actual_timeout == expected_timeout, (
            f"❌ GET_TIMEOUT ERROR: {description}\n"
            f"WHAT FAILED: get_timeout('{language}') returned incorrect value\n"
            f"WHY: Contract POST-2 requires correct timeout lookup\n"
            f"EXPECTED: {expected_timeout} seconds (from TIMEOUT_TEST_CASES)\n"
            f"ACTUAL: {actual_timeout}\n"
            f"GUIDANCE: Implement timeout lookup per POST-2:\n"
            f"  return self.timeout_config.get(language, self.timeout_config['default'])"
        )

    def test_get_timeout_unknown_language_returns_default(self):
        """
        Test get_timeout() returns default for unknown languages.

        CONTRACT: POST-2 (get_timeout)
        - If language not in config, return timeout_config['default']

        WHAT: get_timeout('completely_unknown_lang_xyz') call
        WHY: REQ-4 requires graceful handling of unknown languages
        EXPECTED: 3600 seconds (from DEFAULT_TIMEOUTS_SECONDS['default'])
        ACTUAL: {actual_timeout}
        GUIDANCE: get_timeout() must handle unknown languages per POST-2:
            return self.timeout_config.get(language, self.timeout_config['default'])
            - Never raise KeyError for unknown languages
            - Always fall back to 'default' timeout
            - Contract guarantees 'default' key exists
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()
        actual_timeout = timeout_manager.get_timeout("completely_unknown_lang_xyz")

        expected_default = DEFAULT_TIMEOUTS_SECONDS["default"]

        assert actual_timeout == expected_default, (
            f"❌ DEFAULT FALLBACK ERROR: Unknown language did not use default timeout\n"
            f"WHAT FAILED: get_timeout('completely_unknown_lang_xyz') fallback\n"
            f"WHY: POST-2 requires default timeout for unknown languages\n"
            f"EXPECTED: {expected_default} seconds (DEFAULT_TIMEOUTS_SECONDS['default'])\n"
            f"ACTUAL: {actual_timeout}\n"
            f"GUIDANCE: Use dict.get() with default fallback:\n"
            f"  return self.timeout_config.get(language, self.timeout_config['default'])\n"
            f"  Never raise KeyError - always provide default timeout"
        )

    def test_get_timeout_returns_positive_integer(self):
        """
        Test get_timeout() always returns positive integer per INV-1.

        CONTRACT: INV-1, POST-2
        - All timeout values are positive integers (seconds)
        - get_timeout() must return int > 0

        WHAT: get_timeout('any_language') return type and value
        WHY: INV-1 guarantees positive integer timeouts for all languages
        EXPECTED: int type with value > 0
        ACTUAL: type={type(result)}, value={result}
        GUIDANCE: get_timeout() must enforce INV-1:
            - Return type must be int (not float, str, None)
            - Return value must be > 0 (positive timeout)
            - Use contract defaults which satisfy INV-1
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()
        result = timeout_manager.get_timeout("nonexistent_language_xyz")

        assert isinstance(result, int), (
            f"❌ TYPE ERROR: get_timeout() did not return int\n"
            f"WHAT FAILED: get_timeout('nonexistent_language_xyz') type check\n"
            f"WHY: INV-1 requires all timeout values to be integers\n"
            f"EXPECTED: int type\n"
            f"ACTUAL: {type(result)}\n"
            f"GUIDANCE: get_timeout() must return int, not {type(result).__name__}"
        )

        assert result > 0, (
            f"❌ VALUE ERROR: get_timeout() returned non-positive value\n"
            f"WHAT FAILED: get_timeout('nonexistent_language_xyz') value check\n"
            f"WHY: INV-1 requires all timeout values to be positive (> 0)\n"
            f"EXPECTED: value > 0\n"
            f"ACTUAL: {result}\n"
            f"GUIDANCE: get_timeout() must return positive timeout:\n"
            f"  - Use timeout_config['default'] for unknown languages\n"
            f"  - Contract defaults are all > 0"
        )


class TestLSPTimeoutManagerTouch:
    """Test touch() method per contract POST-1."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @freeze_time("2026-01-11 12:00:00")
    def test_touch_updates_last_used_timestamp(self):
        """
        Test touch() updates last_used timestamp for language.

        CONTRACT: POST-1 (touch)
        - last_used[language] updated to current time (deterministic)

        WHAT: touch('python') followed by last_used query (time frozen)
        WHY: REQ-4 requires tracking last-used timestamps for idle detection
        EXPECTED: last_used['python'] == datetime(2026, 1, 11, 12, 0, 0) (exact match)
        ACTUAL: last_used['python'] = {last_used_time}
        GUIDANCE: touch() must update last_used tracking:
            - Maintain dict[str, datetime] for last_used timestamps
            - Update last_used[language] = datetime.now() on touch()
            - Expose get_last_used(language) for test verification
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        frozen_time = datetime(2026, 1, 11, 12, 0, 0)
        timeout_manager.touch("python")

        # Need way to verify timestamp - implementation should provide getter
        try:
            last_used_time = timeout_manager.get_last_used("python")
        except AttributeError:
            pytest.fail(
                "❌ MISSING METHOD: get_last_used() method not found\n"
                "WHAT FAILED: timeout_manager.get_last_used('python')\n"
                "WHY: Tests need to verify POST-1 (last_used timestamp updated)\n"
                "EXPECTED: Method get_last_used(language) -> datetime\n"
                "ACTUAL: AttributeError - method does not exist\n"
                "GUIDANCE: Add getter method for test verification:\n"
                "  def get_last_used(self, language: str) -> datetime:\n"
                "      return self._last_used[language]"
            )

        assert last_used_time is not None, (
            f"❌ TOUCH FAILED: last_used timestamp not set\n"
            f"WHAT FAILED: get_last_used('python') returned None after touch()\n"
            f"WHY: POST-1 requires touch() to update last_used[language]\n"
            f"EXPECTED: datetime instance at {frozen_time}\n"
            f"ACTUAL: None\n"
            f"GUIDANCE: touch() must update last_used tracking:\n"
            f"  self._last_used[language] = datetime.now()"
        )

        assert last_used_time == frozen_time, (
            f"❌ TIMESTAMP ERROR: last_used timestamp does not match frozen time\n"
            f"WHAT FAILED: get_last_used('python') timestamp validation\n"
            f"WHY: POST-1 requires last_used == current time (deterministic test)\n"
            f"EXPECTED: {frozen_time} (exact match with frozen time)\n"
            f"ACTUAL: {last_used_time}\n"
            f"GUIDANCE: touch() must use current time:\n"
            f"  from datetime import datetime\n"
            f"  self._last_used[language] = datetime.now()"
        )

    def test_touch_multiple_languages_independent(self):
        """
        Test touch() maintains independent timestamps per language.

        CONTRACT: POST-1, INV-2
        - Each language has independent last_used timestamp
        - Touching one language does not affect others

        WHAT: touch('python'), sleep, touch('rust'), verify timestamps differ
        WHY: REQ-4 requires per-language timeout tracking (not global)
        EXPECTED: last_used['python'] < last_used['rust'] (different times)
        ACTUAL: python={python_time}, rust={rust_time}
        GUIDANCE: Maintain separate timestamps per language:
            - Use dict[str, datetime] not single datetime variable
            - touch(lang) only updates _last_used[lang], not others
            - Each language tracks its own last-used time independently
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        timeout_manager.touch("python")
        python_time = timeout_manager.get_last_used("python")

        # Small delay to ensure different timestamps
        import time
        time.sleep(0.01)

        timeout_manager.touch("rust")
        rust_time = timeout_manager.get_last_used("rust")

        assert python_time < rust_time, (
            f"❌ INDEPENDENCE ERROR: Language timestamps not independent\n"
            f"WHAT FAILED: Timestamps for python and rust are not distinct\n"
            f"WHY: REQ-4 requires per-language timeout tracking\n"
            f"EXPECTED: python_time < rust_time (touched at different times)\n"
            f"ACTUAL: python={python_time}, rust={rust_time}\n"
            f"GUIDANCE: Use separate dict entries per language:\n"
            f"  self._last_used['python'] = datetime.now()  # only affects python\n"
            f"  self._last_used['rust'] = datetime.now()    # only affects rust"
        )


class TestLSPTimeoutManagerMonitoring:
    """Test async monitoring task per contract POST-3."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_start_monitoring_creates_background_task(self):
        """
        Test start_monitoring() creates and runs background task.

        CONTRACT: POST-3 (start_monitoring)
        - Background task created and running
        - Monitoring runs asynchronously (INV-3)

        WHAT: await start_monitoring() call
        WHY: REQ-4 requires background monitoring for idle LSP detection
        EXPECTED: Background asyncio.Task created and running
        ACTUAL: Task state = {task_state}
        GUIDANCE: start_monitoring() must create async background task:
            - Create asyncio.Task for monitoring loop
            - Store task reference in self._monitoring_task
            - Task should loop with asyncio.sleep(check_interval)
            - Provide is_monitoring() method for test verification
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        await timeout_manager.start_monitoring()

        # Need way to verify monitoring started
        try:
            is_monitoring = timeout_manager.is_monitoring()
        except AttributeError:
            pytest.fail(
                "❌ MISSING METHOD: is_monitoring() method not found\n"
                "WHAT FAILED: timeout_manager.is_monitoring()\n"
                "WHY: Tests need to verify POST-3 (monitoring task running)\n"
                "EXPECTED: Method is_monitoring() -> bool\n"
                "ACTUAL: AttributeError - method does not exist\n"
                "GUIDANCE: Add status method for test verification:\n"
                "  def is_monitoring(self) -> bool:\n"
                "      return self._monitoring_task is not None and not self._monitoring_task.done()"
            )

        assert is_monitoring is True, (
            f"❌ MONITORING NOT STARTED: Background task not running\n"
            f"WHAT FAILED: is_monitoring() returned False after start_monitoring()\n"
            f"WHY: POST-3 requires monitoring task to be created and running\n"
            f"EXPECTED: True (monitoring task is active)\n"
            f"ACTUAL: {is_monitoring}\n"
            f"GUIDANCE: start_monitoring() must create background task:\n"
            f"  self._monitoring_task = asyncio.create_task(self._monitor_loop())\n"
            f"  async def _monitor_loop(self):\n"
            f"      while True:\n"
            f"          await self.check_and_reclaim()\n"
            f"          await asyncio.sleep(self.check_interval)"
        )

    @pytest.mark.asyncio
    async def test_start_monitoring_idempotent(self):
        """
        Test start_monitoring() is idempotent (safe to call multiple times).

        CONTRACT: PRE-3 (start_monitoring)
        - Safe to call multiple times (idempotent)
        - Does not create duplicate tasks

        WHAT: await start_monitoring() called twice
        WHY: REQ-4 requires safe initialization (may be called multiple times)
        EXPECTED: Only one monitoring task running (not duplicates)
        ACTUAL: Task count = {task_count}
        GUIDANCE: start_monitoring() must check if already monitoring:
            - if self.is_monitoring(): return  # already started
            - Only create new task if not already monitoring
            - Prevents duplicate background tasks
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        await timeout_manager.start_monitoring()
        first_call_monitoring = timeout_manager.is_monitoring()

        await timeout_manager.start_monitoring()  # Second call
        second_call_monitoring = timeout_manager.is_monitoring()

        assert first_call_monitoring is True and second_call_monitoring is True, (
            f"❌ IDEMPOTENCY ERROR: start_monitoring() not idempotent\n"
            f"WHAT FAILED: Multiple start_monitoring() calls caused issues\n"
            f"WHY: PRE-3 requires start_monitoring() to be safe to call multiple times\n"
            f"EXPECTED: Both calls succeed, single task remains running\n"
            f"ACTUAL: first={first_call_monitoring}, second={second_call_monitoring}\n"
            f"GUIDANCE: Implement idempotency check:\n"
            f"  async def start_monitoring(self):\n"
            f"      if self.is_monitoring():\n"
            f"          return  # already started\n"
            f"      self._monitoring_task = asyncio.create_task(...)"
        )

    @pytest.mark.asyncio
    async def test_stop_monitoring_cancels_task(self):
        """
        Test stop_monitoring() cancels background task.

        CONTRACT: POST (stop_monitoring)
        - Monitoring task is cancelled
        - Safe to call even if not monitoring

        WHAT: await stop_monitoring() after start_monitoring()
        WHY: REQ-4 requires clean shutdown for resource cleanup
        EXPECTED: is_monitoring() returns False after stop
        ACTUAL: is_monitoring() = {is_monitoring}
        GUIDANCE: stop_monitoring() must cancel monitoring task:
            - Cancel self._monitoring_task if it exists
            - Catch and ignore asyncio.CancelledError
            - Set self._monitoring_task = None
            - Safe to call even if task is None
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        await timeout_manager.start_monitoring()
        assert timeout_manager.is_monitoring() is True

        await timeout_manager.stop_monitoring()
        is_monitoring = timeout_manager.is_monitoring()

        assert is_monitoring is False, (
            f"❌ STOP FAILED: Monitoring task not cancelled\n"
            f"WHAT FAILED: is_monitoring() still True after stop_monitoring()\n"
            f"WHY: stop_monitoring() must cancel background task\n"
            f"EXPECTED: False (monitoring stopped)\n"
            f"ACTUAL: {is_monitoring}\n"
            f"GUIDANCE: stop_monitoring() must cancel task:\n"
            f"  if self._monitoring_task:\n"
            f"      self._monitoring_task.cancel()\n"
            f"      try: await self._monitoring_task\n"
            f"      except asyncio.CancelledError: pass\n"
            f"      self._monitoring_task = None"
        )


class TestLSPTimeoutManagerReclaim:
    """Test check_and_reclaim() method per contract POST-4."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("idle_seconds,timeout_seconds,should_reclaim,description", RECLAIM_TEST_CASES)
    async def test_check_and_reclaim_contract_cases(self, idle_seconds, timeout_seconds, should_reclaim, description):
        """
        Test check_and_reclaim() behavior per contract test cases.

        CONTRACT: POST-4 (reclaim)
        - LSP reclaimed if (now - last_used) > timeout
        - Returns list of reclaimed language names

        WHAT: check_and_reclaim() with idle_seconds={idle_seconds}, timeout={timeout_seconds}
        WHY: {description}
        EXPECTED: should_reclaim={should_reclaim}
        ACTUAL: reclaimed={reclaimed_languages}
        GUIDANCE: check_and_reclaim() must implement idle detection per POST-4:
            - For each language in last_used:
                idle_time = (now - last_used[lang]).total_seconds()
                if idle_time > timeout[lang]:
                    reclaim LSP for lang
            - Return list of reclaimed language names
            - Use verify_idle_detection() from contract for logic
        """
        from serena.lsp_timeout import LSPTimeoutManager

        # Use frozen time for determinism
        with freeze_time("2026-01-11 12:00:00") as frozen_time:
            # Create manager with custom timeout
            custom_timeout = {"test_lang": timeout_seconds, "default": timeout_seconds}
            timeout_manager = LSPTimeoutManager(timeout_config=custom_timeout)

            # Set last_used to specific time in the past (deterministic)
            past_time = datetime(2026, 1, 11, 12, 0, 0) - timedelta(seconds=idle_seconds)
            timeout_manager.touch("test_lang")

            # Manually override timestamp to simulate idle time (need setter or mock)
            try:
                timeout_manager._last_used["test_lang"] = past_time
            except AttributeError:
                pytest.fail(
                    "❌ TEST SETUP ERROR: Cannot set _last_used for testing\n"
                    "WHAT FAILED: timeout_manager._last_used['test_lang'] = past_time\n"
                    "WHY: Tests need to simulate idle scenarios for reclaim testing\n"
                    "EXPECTED: _last_used dict accessible for test setup\n"
                    "ACTUAL: AttributeError - dict does not exist or is private\n"
                    "GUIDANCE: Maintain _last_used as dict[str, datetime]:\n"
                    "  self._last_used: dict[str, datetime] = {}\n"
                    "  Or provide set_last_used() method for testing"
                )

            # Mock the LSP shutdown to verify it's called
            reclaim_callback = Mock()
            timeout_manager.set_reclaim_callback(reclaim_callback)

            reclaimed_languages = await timeout_manager.check_and_reclaim()

        if should_reclaim:
            assert "test_lang" in reclaimed_languages, (
                f"❌ RECLAIM FAILED: {description}\n"
                f"WHAT FAILED: check_and_reclaim() did not reclaim idle LSP\n"
                f"WHY: POST-4 requires reclaim when (idle_time > timeout)\n"
                f"EXPECTED: 'test_lang' in reclaimed list (idle={idle_seconds}s > timeout={timeout_seconds}s)\n"
                f"ACTUAL: reclaimed={reclaimed_languages}\n"
                f"GUIDANCE: Implement idle detection per verify_idle_detection():\n"
                f"  idle_time = (datetime.now() - last_used[lang]).total_seconds()\n"
                f"  if idle_time > timeout[lang]: reclaim(lang)"
            )
        else:
            assert "test_lang" not in reclaimed_languages, (
                f"❌ FALSE RECLAIM: {description}\n"
                f"WHAT FAILED: check_and_reclaim() reclaimed active LSP\n"
                f"WHY: POST-4 requires reclaim ONLY when (idle_time > timeout)\n"
                f"EXPECTED: 'test_lang' NOT in reclaimed list (idle={idle_seconds}s <= timeout={timeout_seconds}s)\n"
                f"ACTUAL: reclaimed={reclaimed_languages}\n"
                f"GUIDANCE: Check boundary condition (> not >=):\n"
                f"  if idle_time > timeout:  # strictly greater, not equal"
            )

    @pytest.mark.asyncio
    async def test_check_and_reclaim_calls_lsp_manager_shutdown(self):
        """
        Test check_and_reclaim() integrates with LSPManager for actual shutdown.

        WHAT: check_and_reclaim() with idle LSP and mocked LSPManager
        WHY: REQ-4 requires actual LSP shutdown to free memory resources
        EXPECTED: LSPManager.shutdown_language(lang) called for idle languages
        ACTUAL: shutdown_language calls = {calls}
        GUIDANCE: check_and_reclaim() must integrate with LSPManager:
            - Accept lsp_manager in constructor (optional for testing)
            - For each idle language, call: lsp_manager.shutdown_language(lang)
            - Only call if lsp_manager is provided (test mode may omit)
            - Use callback pattern: set_reclaim_callback(callback) for testing
        """
        from serena.lsp_timeout import LSPTimeoutManager

        # Create manager with mock callback
        timeout_manager = LSPTimeoutManager(timeout_config={"test_lang": 1800})

        # Set last_used to expired time
        past_time = datetime.now() - timedelta(seconds=2000)  # Past 30min timeout
        timeout_manager.touch("test_lang")
        timeout_manager._last_used["test_lang"] = past_time

        # Mock reclaim callback
        reclaim_callback = Mock()
        timeout_manager.set_reclaim_callback(reclaim_callback)

        reclaimed = await timeout_manager.check_and_reclaim()

        assert reclaim_callback.called, (
            f"❌ INTEGRATION ERROR: Reclaim callback not called\n"
            f"WHAT FAILED: set_reclaim_callback() callback not invoked on reclaim\n"
            f"WHY: REQ-4 requires actual LSP shutdown for resource cleanup\n"
            f"EXPECTED: reclaim_callback('test_lang') called once\n"
            f"ACTUAL: reclaim_callback.called = {reclaim_callback.called}\n"
            f"GUIDANCE: Invoke callback on reclaim:\n"
            f"  if self._reclaim_callback:\n"
            f"      self._reclaim_callback(language)\n"
            f"  Or: if self._lsp_manager:\n"
            f"      await self._lsp_manager.shutdown_language(language)"
        )

        # Verify callback called with correct language
        reclaim_callback.assert_called_with("test_lang")

    @pytest.mark.asyncio
    async def test_check_and_reclaim_returns_empty_list_when_all_active(self):
        """
        Test check_and_reclaim() returns empty list when no LSPs are idle.

        CONTRACT: POST-4
        - Returns list of reclaimed language names
        - Empty list when no languages are idle

        WHAT: check_and_reclaim() with all recently touched languages
        WHY: Verify correct behavior when no reclamation needed
        EXPECTED: Empty list [] (no languages reclaimed)
        ACTUAL: {reclaimed}
        GUIDANCE: check_and_reclaim() must return empty list when no idle LSPs:
            - Check ALL languages in last_used
            - Only reclaim if idle_time > timeout
            - Return empty list if no languages meet reclaim criteria
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        # Touch multiple languages recently
        timeout_manager.touch("python")
        timeout_manager.touch("rust")
        timeout_manager.touch("typescript")

        reclaimed = await timeout_manager.check_and_reclaim()

        assert reclaimed == [], (
            f"❌ FALSE RECLAIM: Reclaimed active languages\n"
            f"WHAT FAILED: check_and_reclaim() reclaimed recently active LSPs\n"
            f"WHY: POST-4 requires reclaim ONLY for idle languages\n"
            f"EXPECTED: [] (empty list - all languages recently touched)\n"
            f"ACTUAL: {reclaimed}\n"
            f"GUIDANCE: Only reclaim languages with idle_time > timeout:\n"
            f"  reclaimed = []\n"
            f"  for lang, last_used in self._last_used.items():\n"
            f"      if (now - last_used).total_seconds() > self.get_timeout(lang):\n"
            f"          reclaimed.append(lang)\n"
            f"  return reclaimed"
        )


class TestLSPTimeoutManagerIntegration:
    """Integration tests for LSPTimeoutManager with LSPManager."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_set_reclaim_callback_method_exists(self):
        """
        Test set_reclaim_callback() method for LSPManager integration.

        WHAT: timeout_manager.set_reclaim_callback(callback) call
        WHY: Tests need to verify LSP shutdown integration without full LSPManager
        EXPECTED: Method exists and stores callback for later invocation
        ACTUAL: Method {exists_or_missing}
        GUIDANCE: Provide callback setter for flexible integration:
            def set_reclaim_callback(self, callback):
                self._reclaim_callback = callback
            In production: callback = lsp_manager.shutdown_language
            In tests: callback = Mock() for verification
        """
        from serena.lsp_timeout import LSPTimeoutManager

        timeout_manager = LSPTimeoutManager()

        callback = Mock()

        try:
            timeout_manager.set_reclaim_callback(callback)
        except AttributeError:
            pytest.fail(
                "❌ MISSING METHOD: set_reclaim_callback() method not found\n"
                "WHAT FAILED: timeout_manager.set_reclaim_callback(callback)\n"
                "WHY: Tests need to mock LSPManager integration for verification\n"
                "EXPECTED: Method set_reclaim_callback(callback) -> None\n"
                "ACTUAL: AttributeError - method does not exist\n"
                "GUIDANCE: Add callback setter for flexible integration:\n"
                "  def set_reclaim_callback(self, callback):\n"
                "      self._reclaim_callback = callback\n"
                "  Then in check_and_reclaim():\n"
                "      if self._reclaim_callback:\n"
                "          self._reclaim_callback(language)"
            )

    @pytest.mark.asyncio
    async def test_monitoring_loop_calls_check_and_reclaim_periodically(self):
        """
        Test monitoring loop calls check_and_reclaim() at regular intervals.

        CONTRACT: INV-3, POST-3
        - Monitoring runs asynchronously without blocking
        - check_interval defines periodic check frequency (60s recommended)

        WHAT: start_monitoring() with short check_interval for testing
        WHY: REQ-4 requires background monitoring to automatically reclaim idle LSPs
        EXPECTED: check_and_reclaim() called multiple times over time
        ACTUAL: Call count = {call_count} after {duration} seconds
        GUIDANCE: Monitoring loop must call check_and_reclaim() periodically:
            async def _monitor_loop(self):
                while True:
                    await self.check_and_reclaim()
                    await asyncio.sleep(self.check_interval)
            Accept check_interval parameter (default 60 seconds)
            For testing, use short interval (e.g., 0.1 seconds)
        """
        from serena.lsp_timeout import LSPTimeoutManager

        # Create manager with short check interval for testing
        try:
            timeout_manager = LSPTimeoutManager(check_interval=0.1)
        except TypeError:
            pytest.fail(
                "❌ MISSING PARAMETER: check_interval parameter not accepted\n"
                "WHAT FAILED: LSPTimeoutManager(check_interval=0.1)\n"
                "WHY: Monitoring needs configurable interval for production/testing\n"
                "EXPECTED: Constructor accepts check_interval parameter (default 60)\n"
                "ACTUAL: TypeError - parameter not accepted\n"
                "GUIDANCE: Add check_interval parameter:\n"
                "  def __init__(self, timeout_config=None, check_interval=60):\n"
                "      self.check_interval = check_interval"
            )

        # Mock check_and_reclaim to count calls
        original_check = timeout_manager.check_and_reclaim
        call_count = 0

        async def mock_check():
            nonlocal call_count
            call_count += 1
            return []

        timeout_manager.check_and_reclaim = mock_check

        await timeout_manager.start_monitoring()

        # Wait for multiple check cycles
        await asyncio.sleep(0.35)  # Should get ~3 calls at 0.1s interval

        await timeout_manager.stop_monitoring()

        assert call_count >= 2, (
            f"❌ MONITORING LOOP ERROR: check_and_reclaim() not called periodically\n"
            f"WHAT FAILED: Monitoring loop did not call check_and_reclaim() multiple times\n"
            f"WHY: INV-3 requires async monitoring without blocking\n"
            f"EXPECTED: >= 2 calls (with 0.1s interval over 0.35s)\n"
            f"ACTUAL: {call_count} calls\n"
            f"GUIDANCE: Implement monitoring loop:\n"
            f"  async def _monitor_loop(self):\n"
            f"      while True:\n"
            f"          await self.check_and_reclaim()\n"
            f"          await asyncio.sleep(self.check_interval)"
        )
