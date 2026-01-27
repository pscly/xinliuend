from __future__ import annotations

import pytest

from flow_backend.db import get_engine, reset_engine_cache


@pytest.fixture(autouse=True)
def _dispose_engine_after_test():
    """避免 aiosqlite worker 线程在事件循环关闭后回调，导致 PytestUnhandledThreadExceptionWarning。

    注意：这里使用 AsyncEngine.sync_engine.dispose() 以兼容同步/异步两类测试用例。
    """
    yield
    try:
        get_engine().sync_engine.dispose()
    except Exception:
        pass
    reset_engine_cache()
