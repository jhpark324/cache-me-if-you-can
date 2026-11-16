import asyncio
import logging

import pytest

from cache_me.background import run_periodic
from cache_me.records import DomainError


def test_periodic_worker_survives_transient_failures_without_leaking_payload(caplog):
    calls = []

    async def operation():
        calls.append(len(calls) + 1)
        if len(calls) <= 2:
            raise RuntimeError("secret-token and private record body")
        if len(calls) == 4:
            raise asyncio.CancelledError()

    with caplog.at_level(logging.WARNING):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_periodic(operation, interval=0, name="concepts"))
    assert calls == [1, 2, 3, 4]
    assert len(caplog.records) == 1
    assert "concepts" in caplog.text
    assert "secret-token" not in caplog.text and "private record" not in caplog.text


def test_worker_waiting_for_explicit_index_preparation_is_quiet(caplog):
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise DomainError("INDEX_NOT_READY", "not prepared")
        raise asyncio.CancelledError()

    with caplog.at_level(logging.WARNING):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run_periodic(operation, interval=0, name="index",
                ignored_codes=frozenset({"INDEX_NOT_READY"})))
    assert calls == 2
    assert not caplog.records
