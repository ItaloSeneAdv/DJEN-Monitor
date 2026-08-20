from djen_monitor.time_utils import brasilia_now, brasilia_today


def test_brasilia_clock_is_timezone_aware():
    now = brasilia_now()
    assert now.tzinfo is not None
    assert now.date() == brasilia_today()
    assert now.utcoffset() is not None
