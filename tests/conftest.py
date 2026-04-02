"""Global test configuration — ensures clean isolation between test modules."""

import os
import shutil
import tempfile

_test_tmpdirs = {}


def pytest_runtest_setup(item):
    """Give each test_mcp* / test_webhooks test a pristine project dir."""
    module = item.module.__name__
    if "test_mcp" in module or "test_webhooks" in module:
        try:
            import memoria.mcp.server as srv
            srv._reset_singletons()
            td = tempfile.mkdtemp(prefix="memoria_test_")
            _test_tmpdirs[item.nodeid] = td
            srv._PROJECT_DIR = td
            # Clear MEMORIA_DATA_DIR to prevent cross-test pollution
            os.environ.pop("MEMORIA_DATA_DIR", None)
        except (ImportError, AttributeError):
            pass


def pytest_runtest_teardown(item, nextitem):
    """Clean up per-test tmp dirs."""
    td = _test_tmpdirs.pop(item.nodeid, None)
    if td:
        shutil.rmtree(td, ignore_errors=True)
