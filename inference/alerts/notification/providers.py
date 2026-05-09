from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections import deque
from typing import Any

from inference.alerts.alert_models import Alert

logger = logging.getLogger(__name__)


class NotificationProvider(ABC):
    channel_name = "provider"

    @abstractmethod
    def send(self, alert: Alert) -> dict:
        raise NotImplementedError


class WebhookProvider(NotificationProvider):
    channel_name = "webhook"

    def __init__(self, url: str, timeout_seconds: float = 3.0) -> None:
        self._url = url
        self._timeout = timeout_seconds

    def send(self, alert: Alert) -> dict:
        if not self._url:
            return {
                "success": False,
                "channel": self.channel_name,
                "error": "webhook URL is not configured",
                "timestamp": time.time(),
            }
        payload = json.dumps({"alert": alert.to_dict()}).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return {
                    "success": 200 <= int(response.status) < 300,
                    "channel": self.channel_name,
                    "status_code": int(response.status),
                    "timestamp": time.time(),
                }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("Webhook alert dispatch failed for %s: %s", alert.alert_id, exc)
            return {
                "success": False,
                "channel": self.channel_name,
                "error": str(exc),
                "timestamp": time.time(),
            }


class SimulatedSMSProvider(NotificationProvider):
    channel_name = "simulated_sms"

    def __init__(self, recipients: list[str] | None = None, max_records: int = 1_000) -> None:
        self._recipients = list(recipients or [])
        self._records: deque[dict] = deque(maxlen=max_records)

    def send(self, alert: Alert) -> dict:
        record = {
            "success": True,
            "channel": self.channel_name,
            "recipients": list(self._recipients),
            "alert_id": alert.alert_id,
            "message": f"{alert.severity.value.upper()} {alert.title}",
            "timestamp": time.time(),
        }
        self._records.append(record)
        logger.info("Simulated SMS alert dispatch: %s", record)
        return record

    def records(self, limit: int = 100) -> list[dict]:
        return list(self._records)[-max(0, limit):]


class ConsoleProvider(NotificationProvider):
    channel_name = "console"

    def send(self, alert: Alert) -> dict:
        logger.info("Alert dispatch console provider: %s", alert.to_dict())
        return {
            "success": True,
            "channel": self.channel_name,
            "alert_id": alert.alert_id,
            "timestamp": time.time(),
        }


def build_providers(config: dict[str, Any]) -> dict[str, NotificationProvider]:
    providers: dict[str, NotificationProvider] = {}
    webhook_cfg = config.get("webhook", {})
    if webhook_cfg.get("enabled", False):
        providers["webhook"] = WebhookProvider(
            url=str(webhook_cfg.get("url", "")),
            timeout_seconds=float(webhook_cfg.get("timeout_seconds", 3.0)),
        )
    sms_cfg = config.get("simulated_sms", {})
    if sms_cfg.get("enabled", True):
        providers["simulated_sms"] = SimulatedSMSProvider(
            recipients=[str(value) for value in sms_cfg.get("recipients", [])]
        )
    console_cfg = config.get("console", {})
    if console_cfg.get("enabled", True):
        providers["console"] = ConsoleProvider()
    return providers
