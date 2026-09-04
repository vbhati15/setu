from backend.app.formatting import format_rupees
from backend.app.trust.daily_spend import DailySpendTracker


def test_no_prior_spend_allows_purchase_under_cap():
    tracker = DailySpendTracker()
    ok, reason = tracker.check("agent-1", 1000, cap_paise=5000)
    assert ok


def test_recorded_spend_accumulates_toward_cap():
    tracker = DailySpendTracker()
    now = 1_000_000.0
    tracker.record("agent-1", 2000, now=now)
    tracker.record("agent-1", 2000, now=now + 10)
    ok, reason = tracker.check("agent-1", 1001, cap_paise=5000, now=now + 20)
    assert not ok
    assert "agent-1" in reason
    # The reason must be in rupees, not raw paise -- this exact assertion
    # used to check for a bare "5000" (the cap in *paise*), which is the
    # precise bug this whole formatting utility exists to prevent.
    assert format_rupees(5000) in reason
    assert "5000" not in reason


def test_purchase_that_fits_exactly_at_cap_is_allowed():
    tracker = DailySpendTracker()
    now = 1_000_000.0
    tracker.record("agent-1", 3000, now=now)
    ok, reason = tracker.check("agent-1", 2000, cap_paise=5000, now=now + 5)
    assert ok


def test_spend_older_than_24h_falls_out_of_window():
    tracker = DailySpendTracker()
    now = 1_000_000.0
    tracker.record("agent-1", 4000, now=now)
    ok, reason = tracker.check("agent-1", 4000, cap_paise=5000, now=now + 86_401)
    assert ok, "spend older than the 24h window should no longer count"


def test_agents_are_isolated():
    tracker = DailySpendTracker()
    now = 1_000_000.0
    tracker.record("agent-1", 4000, now=now)
    ok, _ = tracker.check("agent-2", 4000, cap_paise=5000, now=now + 1)
    assert ok
