# app/models_risk.py
"""
Risk Assessment and Analytics Models for GeoVision Platform

Supports:
- Risk scores per dataset and site
- Cross-sector alerts (Mining, Infrastructure, Agriculture, etc.)
- Historical risk tracking
- Automated alert generation
- Metrics and KPIs storage
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Integer,
    Index,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid():
    return str(uuid.uuid4())


# ============ ENUMS ============

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(str, Enum):
    # Mining risks
    SLOPE_STABILITY = "slope_stability"
    SUBSIDENCE = "subsidence"
    WATER_ACCUMULATION = "water_accumulation"
    BLAST_ZONE = "blast_zone"
    EQUIPMENT_SAFETY = "equipment_safety"
    
    # Infrastructure risks
    STRUCTURAL_INTEGRITY = "structural_integrity"
    FOUNDATION = "foundation"
    SETTLEMENT = "settlement"
    CRACK_DETECTION = "crack_detection"
    CORROSION = "corrosion"
    
    # Agriculture risks
    CROP_HEALTH = "crop_health"
    PEST_DETECTION = "pest_detection"
    IRRIGATION = "irrigation"
    SOIL_EROSION = "soil_erosion"
    DROUGHT_STRESS = "drought_stress"
    
    # General
    ENVIRONMENTAL = "environmental"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    WEATHER = "weather"
    OPERATIONAL = "operational"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


class AlertPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"
    IN_APP = "in_app"


# ============ RISK SCORES ============

class RiskScore(Base):
    """
    Risk score calculation for a site or dataset.
    Stores historical risk assessments.
    """
    __tablename__ = "risk_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Links
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Sector
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Risk Assessment
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default=RiskLevel.LOW.value)
    
    # Score (0-100)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    
    # Component Scores (JSON)
    component_scores: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Example: {"slope_angle": 85, "water_proximity": 45, "equipment_age": 60}
    
    # Metrics used for calculation (JSON)
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Model/Algorithm Info
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    calculation_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Confidence
    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00
    
    # Assessment Period
    assessment_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    site = relationship("Site")
    dataset = relationship("Dataset")
    alerts = relationship("RiskAlert", back_populates="risk_score")

    __table_args__ = (
        Index("idx_risk_scores_company", "company_id"),
        Index("idx_risk_scores_site", "site_id"),
        Index("idx_risk_scores_category", "risk_category"),
        Index("idx_risk_scores_level", "risk_level"),
        Index("idx_risk_scores_date", "assessment_date"),
        Index("idx_risk_scores_latest", "is_latest"),
    )


# ============ RISK ALERTS ============

class RiskAlert(Base):
    """
    Alert generated from risk assessment.
    Cross-sector alert system.
    """
    __tablename__ = "risk_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Links
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("risk_scores.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Alert Info
    alert_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Classification
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default=AlertPriority.MEDIUM.value)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default=RiskLevel.MEDIUM.value)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=AlertStatus.ACTIVE.value)
    
    # Timestamps
    triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Escalation
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Resolution
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Location (for mapping)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    affected_area_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # GeoJSON
    
    # Recommendations (JSON)
    recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    site = relationship("Site")
    risk_score = relationship("RiskScore", back_populates="alerts")
    acknowledged_by = relationship("User", foreign_keys=[acknowledged_by_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    events = relationship("AlertEvent", back_populates="alert", cascade="all, delete-orphan")
    notifications = relationship("AlertNotification", back_populates="alert", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_risk_alerts_company", "company_id"),
        Index("idx_risk_alerts_site", "site_id"),
        Index("idx_risk_alerts_status", "status"),
        Index("idx_risk_alerts_severity", "severity"),
        Index("idx_risk_alerts_triggered", "triggered_at"),
        Index("idx_risk_alerts_sector", "sector"),
    )


# ============ ALERT EVENTS (TIMELINE) ============

class AlertEvent(Base):
    """
    Historical events for an alert.
    Tracks status changes, comments, actions.
    """
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("risk_alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Event Info
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # status_change, comment, escalation, notification_sent, action_taken, etc.
    
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status Change
    previous_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # Actor
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    alert = relationship("RiskAlert", back_populates="events")
    user = relationship("User")

    __table_args__ = (
        Index("idx_alert_events_alert", "alert_id"),
        Index("idx_alert_events_type", "event_type"),
    )


# ============ ALERT NOTIFICATIONS ============

class AlertNotification(Base):
    """
    Notifications sent for alerts.
    Tracks delivery status.
    """
    __tablename__ = "alert_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("risk_alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Recipient
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    recipient_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Channel
    notification_type: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Content
    subject: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, sent, delivered, failed, read
    
    # Delivery Info
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Provider
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    alert = relationship("RiskAlert", back_populates="notifications")
    user = relationship("User")

    __table_args__ = (
        Index("idx_alert_notifications_alert", "alert_id"),
        Index("idx_alert_notifications_status", "status"),
        Index("idx_alert_notifications_type", "notification_type"),
    )


# ============ SITE METRICS (KPIs) ============

class SiteMetrics(Base):
    """
    KPI and metrics storage for sites.
    Time-series data for dashboards.
    """
    __tablename__ = "site_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Links
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Metric Info
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Value
    value_numeric: Mapped[Optional[float]] = mapped_column(Numeric(20, 6), nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    value_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSONB in PostgreSQL
    
    # Unit
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Timestamp
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    period: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # daily, weekly, monthly
    
    # Source
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # dataset, sensor, manual, api
    dataset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    site = relationship("Site")

    __table_args__ = (
        Index("idx_site_metrics_company", "company_id"),
        Index("idx_site_metrics_site", "site_id"),
        Index("idx_site_metrics_name", "metric_name"),
        Index("idx_site_metrics_recorded", "recorded_at"),
        Index("idx_site_metrics_category", "metric_category"),
    )


# ============ ALERT RULES ============

class AlertRule(Base):
    """
    Configurable rules for automatic alert generation.
    """
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    # Scope
    company_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # Null = global
    site_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Rule Info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Sector
    sector: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Null = all sectors
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Conditions (JSON)
    conditions: Mapped[str] = mapped_column(Text, nullable=False)
    # Example: {"metric": "slope_angle", "operator": ">", "value": 45}
    
    # Alert Config
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default=AlertPriority.MEDIUM.value)
    alert_title_template: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_description_template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Thresholds
    threshold_low: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    threshold_medium: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    threshold_high: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    threshold_critical: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Cooldown (avoid alert spam)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Notification settings
    notification_channels: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    auto_escalate_after_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_alert_rules_company", "company_id"),
        Index("idx_alert_rules_active", "is_active"),
        Index("idx_alert_rules_category", "risk_category"),
    )


# ============ SECTOR THRESHOLDS ============

class SectorThreshold(Base):
    """
    Default thresholds per sector.
    Used by alert rules if not overridden.
    """
    __tablename__ = "sector_thresholds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Thresholds
    threshold_low: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    threshold_medium: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    threshold_high: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    threshold_critical: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Units
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sector_thresholds_sector", "sector"),
        Index("idx_sector_thresholds_category", "risk_category"),
    )
