import pytest

from backend.app.trust.retry import RetryExhausted, retry_with_backoff


def test_succeeds_first_try_no_retry_needed():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, sleep=lambda s: None)
    assert result == "ok"
    assert len(calls) == 1


def test_retries_transient_error_then_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("simulated timeout")
        return "ok"

    result = retry_with_backoff(fn, max_attempts=5, sleep=lambda s: None)
    assert result == "ok"
    assert len(calls) == 3


def test_gives_up_after_max_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise TimeoutError("always fails")

    with pytest.raises(RetryExhausted):
        retry_with_backoff(fn, max_attempts=3, sleep=lambda s: None)
    assert len(calls) == 3


def test_non_retriable_exception_propagates_immediately():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("not a transient error")

    with pytest.raises(ValueError):
        retry_with_backoff(fn, max_attempts=5, sleep=lambda s: None)
    assert len(calls) == 1
