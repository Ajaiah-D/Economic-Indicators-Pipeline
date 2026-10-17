"""
Retries for FRED API calls, shared by the three ingestion scripts.

fredapi 0.5.1 catches every urllib HTTPError and raises
ValueError(<message attribute of the XML error body>) from inside the except
block, so the HTTPError survives only as the ValueError's __context__. When
FRED answers a transient 5xx with no message, that is ValueError(None) and
the log just says "None".

Transient failures (HTTP 429 or 5xx, connection errors, timeouts) are retried
with exponential backoff. Anything else, e.g. HTTP 400 "series does not
exist", fails on the first attempt. The final error names the HTTP status
instead of "None".

Backoff waits are 2s, 4s, 8s, so a retried series sends at most one extra
request every couple of seconds -- far inside FRED's 120 requests/minute.
"""

import http.client
import logging
import time
import urllib.error

logger = logging.getLogger(__name__)

ATTEMPTS = 4
BASE_DELAY_SECONDS = 2.0

# patched in tests so they never actually sleep
_sleep = time.sleep


class FredRequestError(RuntimeError):
    """A FRED call that failed for good; the message says why."""


def _chained_http_error(exc: BaseException) -> urllib.error.HTTPError | None:
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, urllib.error.HTTPError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


def is_transient(exc: BaseException) -> bool:
    http_error = _chained_http_error(exc)
    if http_error is not None:
        return http_error.code == 429 or 500 <= http_error.code <= 599
    return isinstance(
        exc, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)
    )


def describe(exc: BaseException) -> str:
    """'HTTP 503 Service Unavailable' rather than fredapi's bare 'None'."""
    message = str(exc)
    if message in ("", "None"):
        message = ""
    http_error = _chained_http_error(exc)
    if http_error is not None:
        status = f"HTTP {http_error.code} {http_error.reason}".rstrip()
        return f"{status}: {message}" if message else status
    return message or type(exc).__name__


def call_with_retry(fn, *args, attempts: int = ATTEMPTS, base_delay: float = BASE_DELAY_SECONDS, **kwargs):
    """Call fn(*args, **kwargs), retrying transient FRED failures with backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not is_transient(exc):
                raise FredRequestError(describe(exc)) from exc
            if attempt == attempts:
                raise FredRequestError(f"{describe(exc)} (after {attempts} attempts)") from exc
            delay = base_delay * 2 ** (attempt - 1)
            logger.warning(
                "FRED call %s failed (%s); retry %d/%d in %.0fs",
                args[0] if args else "", describe(exc), attempt, attempts - 1, delay,
            )
            _sleep(delay)
