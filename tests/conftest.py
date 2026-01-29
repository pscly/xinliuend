from __future__ import annotations


from flow_backend.db import dispose_engine_cache


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    # Safety net: close cached engine so CI can exit cleanly.
    dispose_engine_cache()
