import datetime

from manifexa.app import _five_year_window, _year_window


def test_window_normal_day():
    assert _five_year_window(datetime.date(2026, 7, 13)) == (2026, "2021-07-13")


def test_year_window_configurable():
    assert _year_window(datetime.date(2026, 7, 13), 3) == (2026, "2023-07-13")
    assert _year_window(datetime.date(2026, 7, 13), 2) == (2026, "2024-07-13")
    assert _five_year_window(datetime.date(2026, 7, 13)) == _year_window(datetime.date(2026, 7, 13), 5)


def test_window_survives_leap_day():
    # year-5 of any leap year is never a leap year, so Feb 29 can't be reused
    y, frm = _five_year_window(datetime.date(2024, 2, 29))
    assert y == 2024
    datetime.date.fromisoformat(frm)            # must be a VALID date, not raise
    assert frm == "2019-02-28"
