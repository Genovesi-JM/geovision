from datetime import UTC, datetime, timedelta

from app.time_utils import utc_from_timestamp, utc_now


def test_utc_now_preserves_naive_database_contract():
    before = datetime.now(UTC).replace(tzinfo=None)
    value = utc_now()
    after = datetime.now(UTC).replace(tzinfo=None)

    assert value.tzinfo is None
    assert before <= value <= after


def test_utc_from_timestamp_returns_naive_utc():
    value = utc_from_timestamp(1_700_000_000)

    assert value.tzinfo is None
    assert value == datetime(2023, 11, 14, 22, 13, 20)


def test_utc_values_remain_compatible_with_existing_timedelta_math():
    value = utc_now()

    assert (value + timedelta(minutes=5)) - value == timedelta(minutes=5)
