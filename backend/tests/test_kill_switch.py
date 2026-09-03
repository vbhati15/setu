from app.trust.kill_switch import KillSwitch


def test_starts_inactive():
    switch = KillSwitch()
    assert switch.is_active is False


def test_activate_sets_active_and_reason():
    switch = KillSwitch()
    switch.activate("suspected fraud spike")
    assert switch.is_active is True
    assert switch.reason == "suspected fraud spike"


def test_deactivate_clears_state():
    switch = KillSwitch()
    switch.activate("test")
    switch.deactivate()
    assert switch.is_active is False
    assert switch.reason is None
