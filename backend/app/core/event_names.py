"""Canonical internal event vocabulary.

Names describe facts in past tense. Commands that intentionally request later
work use ``*.requested``. Keeping this list provider-neutral prevents Azure,
ERP, MQTT, or storage payload names from leaking into domain modules.
"""

from __future__ import annotations


class EventNames:
    ORGANIZATION_CREATED = "organization.created"
    ORGANIZATION_UPDATED = "organization.updated"
    ORGANIZATION_MEMBER_ADDED = "organization.member_added"
    ORGANIZATION_MEMBER_INVITED = "organization.member_invited"
    ORGANIZATION_MEMBER_UPDATED = "organization.member_updated"
    ORGANIZATION_MEMBER_REMOVED = "organization.member_removed"

    ORDER_CREATED = "order.created"
    ORDER_STATE_CHANGED = "order.state_changed"
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_SETTLED = "payment.settled"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_STATE_CHANGED = "payment.state_changed"

    FULFILMENT_JOB_CREATED = "fulfilment_job.created"
    FULFILMENT_JOB_DEPENDENCY_ADDED = "fulfilment_job.dependency_added"
    FULFILMENT_JOB_ASSIGNMENT_CHANGED = "fulfilment_job.assignment_changed"
    FULFILMENT_JOB_SCHEDULE_CHANGED = "fulfilment_job.schedule_changed"
    FULFILMENT_JOB_DEPENDENCIES_SATISFIED = "fulfilment_job.dependencies_satisfied"
    FULFILMENT_JOB_STATE_CHANGED = "fulfilment_job.state_changed"

    ACQUISITION_CREATED = "acquisition.created"
    ACQUISITION_UPDATED = "acquisition.updated"
    ACQUISITION_STATE_CHANGED = "acquisition.state_changed"
    ACQUISITION_UPLOAD_COMPLETED = "acquisition.upload_completed"

    DATASET_CREATED = "dataset.created"
    DATASET_UPLOAD_RESERVED = "dataset.upload_reserved"
    DATASET_FILE_UPLOADED = "dataset.file_uploaded"
    DATASET_FILE_DELETED = "dataset.file_deleted"
    DATASET_INGESTION_REQUESTED = "dataset.ingestion_requested"
    DATASET_READY = "dataset.ready"
    DATASET_ARCHIVED = "dataset.archived"

    PROCESSING_REQUESTED = "processing.requested"
    PROCESSING_NEEDS_REVIEW = "processing.needs_review"
    PROCESSING_COMPLETED = "processing.completed"
    PROCESSING_FAILED = "processing.failed"
    PROCESSING_CANCELLED = "processing.cancelled"
    OBSERVATION_CREATED = "observation.created"
    KPI_UPDATED = "kpi.updated"
    ACTION_REQUESTED = "action.requested"
    ACTION_COMPLETED = "action.completed"
    REPORT_PUBLISHED = "report.published"

    DEVICE_TELEMETRY_RECEIVED = "device.telemetry_received"
    DEVICE_STATE_CHANGED = "device.state_changed"
    DEVICE_OFFLINE_DETECTED = "device.offline_detected"
    DEVICE_COMMAND_RESULT_RECORDED = "device.command_result_recorded"

    ERP_SYNC_REQUESTED = "erp.sync_requested"
    ERP_SYNC_COMPLETED = "erp.sync_completed"
    ERP_SYNC_FAILED = "erp.sync_failed"


CANONICAL_EVENT_NAMES = frozenset(
    value
    for name, value in vars(EventNames).items()
    if name.isupper() and isinstance(value, str)
)


__all__ = ["CANONICAL_EVENT_NAMES", "EventNames"]
