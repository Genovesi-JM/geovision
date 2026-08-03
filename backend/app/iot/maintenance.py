from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import TelemetryAggregate, TelemetryReading


BUCKET_SECONDS = 300


def _bucket(value: datetime) -> datetime:
    epoch = int(value.timestamp())
    return datetime.utcfromtimestamp(epoch - epoch % BUCKET_SECONDS)


def aggregate_and_retain(db: Session) -> dict[str, int]:
    """Roll up recent completed buckets and enforce configurable retention.

    This portable worker keeps local SQLite and PostgreSQL behaviour identical.
    Large deployments can replace it with Timescale continuous aggregates while
    retaining the same table/API contract.
    """
    now = datetime.utcnow(); completed_before = _bucket(now)
    recent_after = completed_before - timedelta(minutes=15)
    rows = db.query(TelemetryReading).filter(
        TelemetryReading.numeric_value.is_not(None),
        TelemetryReading.recorded_at >= recent_after,
        TelemetryReading.recorded_at < completed_before,
    ).limit(50000).all()
    groups: dict[tuple, list[float]] = defaultdict(list); details = {}
    for row in rows:
        key = (row.device_id, row.channel, _bucket(row.recorded_at))
        groups[key].append(float(row.numeric_value)); details[key] = row
    for key, values in groups.items():
        device_id, channel, bucket_start = key; source = details[key]
        aggregate = db.query(TelemetryAggregate).filter_by(device_id=device_id, channel=channel, bucket_start=bucket_start, bucket_seconds=BUCKET_SECONDS).first()
        if not aggregate:
            aggregate = TelemetryAggregate(device_id=device_id, company_id=source.company_id, site_id=source.site_id, channel=channel, unit=source.unit, bucket_start=bucket_start, bucket_seconds=BUCKET_SECONDS, sample_count=0, minimum=0, maximum=0, average=0)
            db.add(aggregate)
        aggregate.sample_count = len(values); aggregate.minimum = min(values); aggregate.maximum = max(values); aggregate.average = sum(values) / len(values)
    raw_deleted = db.query(TelemetryReading).filter(TelemetryReading.recorded_at < now - timedelta(days=settings.iot_raw_retention_days)).delete(synchronize_session=False)
    aggregate_deleted = db.query(TelemetryAggregate).filter(TelemetryAggregate.bucket_start < now - timedelta(days=settings.iot_aggregate_retention_days)).delete(synchronize_session=False)
    db.commit()
    return {"buckets": len(groups), "raw_deleted": raw_deleted, "aggregates_deleted": aggregate_deleted}
