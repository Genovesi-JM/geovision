"""Turn stored telemetry into analytical KPIs.

Pure functions over ORM rows (TelemetryReading, SensorChannel, IotAlert) so they
are unit-testable without a database. Used by the JSON analytics endpoint and the
PDF report. All time-integrated figures (run-hours, uptime) are honest estimates
derived from sample density and are labelled as such.
"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from app.time_utils import utc_now


def _num(row) -> float | None:
    if row.numeric_value is not None:
        return float(row.numeric_value)
    if row.boolean_value is not None:
        return 1.0 if row.boolean_value else 0.0
    return None


def _channel_bounds(channels) -> dict:
    return {c.key: c for c in channels}


def compute_device_analytics(device, channels, readings, alerts, start: datetime, end: datetime) -> dict:
    period_seconds = max((end - start).total_seconds(), 1.0)
    period_hours = period_seconds / 3600.0
    bounds = _channel_bounds(channels)

    by_channel: dict[str, list] = {}
    for r in readings:
        by_channel.setdefault(r.channel, []).append(r)

    channel_stats = []
    all_times = [r.recorded_at for r in readings if r.recorded_at is not None]
    for key in sorted(by_channel):
        rows = sorted(by_channel[key], key=lambda r: r.recorded_at or start)
        values = [_num(r) for r in rows]
        values = [v for v in values if v is not None]
        ch = bounds.get(key)
        unit = next((r.unit for r in rows if r.unit), None) or (ch.unit if ch else None)
        data_type = ch.data_type if ch else ("boolean" if all(r.numeric_value is None and r.boolean_value is not None for r in rows) else "number")
        stat = {
            "channel": key, "unit": unit, "data_type": data_type,
            "samples": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "avg": round(sum(values) / len(values), 4) if values else None,
            "last": values[-1] if values else None,
            "bad_quality_samples": sum(1 for r in rows if r.quality in {"bad", "sensor_error"}),
        }
        # Time-in-range against configured channel bounds (numeric only).
        if ch and data_type == "number" and (ch.minimum is not None or ch.maximum is not None) and values:
            lo = ch.minimum if ch.minimum is not None else float("-inf")
            hi = ch.maximum if ch.maximum is not None else float("inf")
            in_range = sum(1 for v in values if lo <= v <= hi)
            stat["time_in_range_pct"] = round(100.0 * in_range / len(values), 1)
        # Duty cycle / estimated run-hours for boolean/run-status channels.
        if data_type == "boolean" and values:
            on_ratio = sum(1 for v in values if v >= 0.5) / len(values)
            stat["on_ratio"] = round(on_ratio, 4)
            stat["estimated_on_hours"] = round(on_ratio * period_hours, 2)
            # rising edges = number of times it switched off->on
            edges = sum(1 for a, b in zip(values, values[1:]) if a < 0.5 <= b)
            stat["activations"] = edges
        channel_stats.append(stat)

    # Data span / completeness proxy: how much of the window is actually covered,
    # plus an expected-sample estimate from the median inter-sample interval.
    data_span_ratio = 0.0
    completeness_pct = None
    if len(all_times) >= 2:
        first, last = min(all_times), max(all_times)
        data_span_ratio = round(min((last - first).total_seconds() / period_seconds, 1.0), 3)
        intervals = sorted((b - a).total_seconds() for a, b in zip(sorted(all_times), sorted(all_times)[1:]))
        intervals = [i for i in intervals if i > 0]
        if intervals:
            cadence = median(intervals)
            expected = period_seconds / cadence if cadence > 0 else len(all_times)
            completeness_pct = round(min(100.0, 100.0 * len(all_times) / expected), 1) if expected else None

    last_seen = device.last_seen_at
    stale = not last_seen or (utc_now() - last_seen).total_seconds() > 120

    # Incident analytics.
    sev_counts: dict[str, int] = {}
    open_states = {"pending", "triggered", "notified", "acknowledged", "assigned"}
    open_count = 0
    ttas, ttrs = [], []
    for a in alerts:
        sev_counts[a.severity] = sev_counts.get(a.severity, 0) + 1
        if a.status in open_states:
            open_count += 1
        if a.acknowledged_at and a.opened_at:
            ttas.append((a.acknowledged_at - a.opened_at).total_seconds())
        if a.resolved_at and a.opened_at:
            ttrs.append((a.resolved_at - a.opened_at).total_seconds())

    incidents = {
        "total": len(alerts), "by_severity": sev_counts, "open": open_count,
        "resolved": sum(1 for a in alerts if a.status in {"resolved", "closed"}),
        "mtta_seconds": round(sum(ttas) / len(ttas), 1) if ttas else None,
        "mttr_seconds": round(sum(ttrs) / len(ttrs), 1) if ttrs else None,
    }

    recommendations = _recommendations(device, channel_stats, incidents, stale, data_span_ratio)

    return {
        "device_uid": device.public_id,
        "period": {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z", "hours": round(period_hours, 1)},
        "overview": {
            "total_readings": len(readings),
            "channels_reporting": len([s for s in channel_stats if s["samples"] > 0]),
            "device_status": device.status,
            "last_seen_at": last_seen.isoformat() + "Z" if last_seen else None,
            "stale": stale,
            "data_span_ratio": data_span_ratio,
            "completeness_pct": completeness_pct,
        },
        "channels": channel_stats,
        "incidents": incidents,
        "recommendations": recommendations,
    }


def _recommendations(device, channel_stats, incidents, stale, data_span_ratio) -> list[str]:
    recs: list[str] = []
    if stale:
        recs.append("Device has no recent heartbeat — check power and connectivity before relying on live data.")
    if incidents["open"] > 0:
        recs.append(f"{incidents['open']} alert(s) still open — acknowledge and resolve them to keep the incident log clean.")
    for s in channel_stats:
        if s["bad_quality_samples"] > 0:
            recs.append(f"Channel '{s['channel']}' reported {s['bad_quality_samples']} bad/sensor-error sample(s) — inspect wiring or recalibrate.")
        if s.get("time_in_range_pct") is not None and s["time_in_range_pct"] < 90:
            recs.append(f"Channel '{s['channel']}' was in range only {s['time_in_range_pct']}% of the time — review thresholds or the process.")
        if s["channel"] == "battery" and s.get("last") is not None and s["last"] < 20:
            recs.append("Battery is low — schedule a replacement or check charging/solar.")
    if data_span_ratio < 0.5 and incidents["total"] >= 0:
        recs.append("Data covers less than half the reporting window — increase sampling reliability or extend uptime.")
    if not recs:
        recs.append("All channels reported within range with no open incidents; continue routine calibration per the manufacturer's interval.")
    return recs
