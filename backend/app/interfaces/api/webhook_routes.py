"""
Webhook endpoints for external service integrations.

Grafana Unified Alerting sends alert notifications here.
These are internal-network endpoints — no user auth required since
only Grafana (inside the Docker network) calls them.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class GrafanaAlert(BaseModel):
    """Single alert from Grafana Unified Alerting payload."""

    status: str  # "firing" or "resolved"
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    starts_at: str = Field("", alias="startsAt")
    ends_at: str = Field("", alias="endsAt")
    generator_url: str = Field("", alias="generatorURL")
    fingerprint: str = ""
    values: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


class GrafanaAlertPayload(BaseModel):
    """Grafana Unified Alerting webhook payload."""

    receiver: str = ""
    status: str = ""  # "firing" or "resolved"
    alerts: list[GrafanaAlert] = []
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(default_factory=dict, alias="commonAnnotations")
    external_url: str = Field("", alias="externalURL")
    version: str = ""
    group_key: str = Field("", alias="groupKey")
    truncated_alerts: int = Field(0, alias="truncatedAlerts")
    org_id: int = Field(0, alias="orgId")
    title: str = ""
    state: str = ""
    message: str = ""

    model_config = {"populate_by_name": True}


@router.post("/grafana-alert")
async def receive_grafana_alert(payload: GrafanaAlertPayload) -> dict[str, str]:
    """Receive alert notifications from Grafana Unified Alerting.

    Logs each alert at the appropriate severity level so they appear
    in Loki via Promtail for historical alert tracking.
    """
    firing = [a for a in payload.alerts if a.status == "firing"]
    resolved = [a for a in payload.alerts if a.status == "resolved"]

    for alert in firing:
        severity = alert.labels.get("severity", "warning")
        log_fn = logger.critical if severity == "critical" else logger.warning
        log_fn(
            "grafana_alert_firing",
            extra={
                "alert_name": alert.labels.get("alertname", "unknown"),
                "severity": severity,
                "category": alert.labels.get("category", ""),
                "summary": alert.annotations.get("summary", ""),
                "description": alert.annotations.get("description", ""),
                "fingerprint": alert.fingerprint,
                "starts_at": alert.starts_at,
                "values": alert.values,
                "receiver": payload.receiver,
            },
        )

    for alert in resolved:
        logger.info(
            "grafana_alert_resolved",
            extra={
                "alert_name": alert.labels.get("alertname", "unknown"),
                "severity": alert.labels.get("severity", ""),
                "category": alert.labels.get("category", ""),
                "summary": alert.annotations.get("summary", ""),
                "fingerprint": alert.fingerprint,
                "resolved_at": alert.ends_at,
                "receiver": payload.receiver,
            },
        )

    logger.info(
        "grafana_webhook_received",
        extra={
            "receiver": payload.receiver,
            "status": payload.status,
            "firing_count": len(firing),
            "resolved_count": len(resolved),
            "group_key": payload.group_key,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    return {"status": "ok", "processed": str(len(payload.alerts))}
