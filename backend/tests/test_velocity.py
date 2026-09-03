from app.trust.velocity import VelocityLimiter


def test_under_limit_is_allowed():
    limiter = VelocityLimiter(max_per_minute=3, max_per_hour=100)
    for _ in range(2):
        ok, reason = limiter.check("agent-1")
        assert ok
        limiter.record("agent-1")


def test_exceeding_per_minute_limit_blocks():
    limiter = VelocityLimiter(max_per_minute=2, max_per_hour=100)
    now = 1_000_000.0
    limiter.record("agent-1", now=now)
    limiter.record("agent-1", now=now + 1)
    ok, reason = limiter.check("agent-1", now=now + 2)
    assert not ok
    assert "agent-1" in reason
    assert "minute" in reason


def test_exceeding_per_hour_limit_blocks():
    limiter = VelocityLimiter(max_per_minute=1000, max_per_hour=2)
    now = 1_000_000.0
    limiter.record("agent-1", now=now)
    limiter.record("agent-1", now=now + 200)
    ok, reason = limiter.check("agent-1", now=now + 400)
    assert not ok
    assert "hour" in reason


def test_window_reset_allows_requests_again():
    limiter = VelocityLimiter(max_per_minute=1, max_per_hour=100)
    now = 1_000_000.0
    limiter.record("agent-1", now=now)
    ok, _ = limiter.check("agent-1", now=now + 1)
    assert not ok
    ok, _ = limiter.check("agent-1", now=now + 61)
    assert ok


def test_agents_are_isolated():
    limiter = VelocityLimiter(max_per_minute=1, max_per_hour=100)
    now = 1_000_000.0
    limiter.record("agent-1", now=now)
    ok, _ = limiter.check("agent-1", now=now + 1)
    assert not ok
    ok, _ = limiter.check("agent-2", now=now + 1)
    assert ok
