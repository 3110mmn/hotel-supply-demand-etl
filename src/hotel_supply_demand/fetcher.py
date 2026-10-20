"""Shared file integrity helpers for official XLSX downloads."""

from __future__ import annotations

import hashlib
import ssl
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from urllib.error import HTTPError, URLError

T = TypeVar("T")

# Low-level connection failures (SSL handshake timeouts, dropped connections,
# DNS hiccups) that are worth a short retry.
TRANSIENT_NETWORK_ERRORS = (URLError, TimeoutError, ssl.SSLError)

# HTTP status codes worth retrying. 404 is here on empirical grounds, not
# HTTP convention: e-Stat has been observed returning a spurious 404 for a
# real, unchanged file when ~90 requests land in quick succession (likely
# rate-limiting/WAF behavior that doesn't bother with 429/503), and a retry
# a few seconds later succeeds. A *persistent* 404 (the file genuinely
# moved/was removed) still surfaces as an error once attempts are exhausted.
RETRYABLE_HTTP_STATUS_CODES = frozenset({404, 429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    pass


def retry_on_transient_network_error(
    call: Callable[[], T], *, attempts: int = 3, backoff_seconds: float = 2.0
) -> T:
    """Retry a network call a few times on timeouts/SSL/connection errors.

    Official statistics sites occasionally stall or drop the TLS handshake,
    or (empirically) answer a real file with a transient error status under
    load. A short retry avoids failing an entire scheduled run (which can
    touch 90+ source files in one pass) over a single blip. Non-retryable
    HTTPErrors (e.g. 304 Not Modified, used by callers for change detection,
    or a definitive 403/410) propagate immediately.
    """
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_STATUS_CODES or attempt == attempts:
                raise
            time.sleep(backoff_seconds * attempt)
        except TRANSIENT_NETWORK_ERRORS:
            if attempt == attempts:
                raise
            time.sleep(backoff_seconds * attempt)
    raise AssertionError("unreachable")  # pragma: no cover


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_xlsx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise FetchError(f"not a valid XLSX file: {path.name}") from exc
    required = {"[Content_Types].xml", "xl/workbook.xml"}
    if not required.issubset(names):
        raise FetchError(f"XLSX structure is incomplete: {path.name}")
