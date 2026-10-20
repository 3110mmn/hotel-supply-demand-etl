import unittest
from urllib.error import HTTPError, URLError

from hotel_supply_demand.fetcher import retry_on_transient_network_error


class RetryOnTransientNetworkErrorTest(unittest.TestCase):
    def test_returns_result_on_first_success(self) -> None:
        self.assertEqual(retry_on_transient_network_error(lambda: 42), 42)

    def test_retries_transient_error_then_succeeds(self) -> None:
        attempts = {"count": 0}

        def call() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise URLError("handshake operation timed out")
            return "ok"

        result = retry_on_transient_network_error(call, attempts=3, backoff_seconds=0)
        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)

    def test_raises_after_exhausting_attempts(self) -> None:
        def call() -> None:
            raise URLError("still timing out")

        with self.assertRaises(URLError):
            retry_on_transient_network_error(call, attempts=2, backoff_seconds=0)

    def test_non_retryable_http_error_is_not_retried(self) -> None:
        attempts = {"count": 0}

        def call() -> None:
            attempts["count"] += 1
            raise HTTPError("https://example.com", 403, "forbidden", None, None)

        with self.assertRaises(HTTPError):
            retry_on_transient_network_error(call, attempts=3, backoff_seconds=0)
        self.assertEqual(attempts["count"], 1)

    def test_transient_404_is_retried_then_succeeds(self) -> None:
        attempts = {"count": 0}

        def call() -> str:
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise HTTPError("https://example.com", 404, "not found", None, None)
            return "ok"

        result = retry_on_transient_network_error(call, attempts=3, backoff_seconds=0)
        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 2)

    def test_persistent_404_raises_after_exhausting_attempts(self) -> None:
        attempts = {"count": 0}

        def call() -> None:
            attempts["count"] += 1
            raise HTTPError("https://example.com", 404, "not found", None, None)

        with self.assertRaises(HTTPError):
            retry_on_transient_network_error(call, attempts=3, backoff_seconds=0)
        self.assertEqual(attempts["count"], 3)


if __name__ == "__main__":
    unittest.main()
