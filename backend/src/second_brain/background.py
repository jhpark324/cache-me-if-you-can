"""Keep periodic local workers alive without logging credentials or record text."""
import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def run_periodic(operation: Callable[[], Awaitable[object]], *, interval: float,
                       name: str, ignored_codes: frozenset[str] = frozenset()):
    reported_failure = False
    while True:
        try:
            await operation()
            reported_failure = False
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # A failed claim/commit must not permanently kill the worker. Job
            # leases and attempt limits remain owned by the domain service.
            if getattr(error, "code", None) not in ignored_codes and not reported_failure:
                logger.warning("Background worker %s failed; retrying on the next cycle.", name)
                reported_failure = True
        await asyncio.sleep(interval)
