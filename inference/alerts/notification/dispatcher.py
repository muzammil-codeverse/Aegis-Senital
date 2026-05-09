from __future__ import annotations

import logging
from typing import Any

from core.event_bus import EventType, get_event_bus
from inference.alerts.alert_models import Alert
from inference.alerts.alert_router import AlertRouter
from inference.alerts.notification.providers import NotificationProvider, build_providers
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(
        self,
        *,
        config: dict | None = None,
        router: AlertRouter | None = None,
        providers: dict[str, NotificationProvider] | None = None,
    ) -> None:
        self._config = config or _safe_provider_config()
        self._router = router or AlertRouter()
        self._providers = providers or build_providers(self._config)

    def dispatch(self, alert: Alert) -> list[dict]:
        results: list[dict] = []
        channels = self._router.channels_for_alert(alert)
        for channel in channels:
            if channel == "websocket":
                results.append(
                    {
                        "success": True,
                        "channel": "websocket",
                        "alert_id": alert.alert_id,
                        "note": "published through event bus for websocket broadcaster",
                    }
                )
                continue
            provider = self._providers.get(channel)
            if provider is None:
                result = {
                    "success": False,
                    "channel": channel,
                    "alert_id": alert.alert_id,
                    "error": f"provider '{channel}' is not enabled",
                }
                results.append(result)
                self._publish_failure(alert, result)
                continue
            try:
                result = provider.send(alert)
            except Exception as exc:
                result = {
                    "success": False,
                    "channel": channel,
                    "alert_id": alert.alert_id,
                    "error": str(exc),
                }
                logger.exception("Alert provider %s raised while dispatching %s", channel, alert.alert_id)
            result.setdefault("alert_id", alert.alert_id)
            result.setdefault("channel", channel)
            results.append(result)
            if not result.get("success", False):
                self._publish_failure(alert, result)
        return results

    @property
    def providers(self) -> dict[str, NotificationProvider]:
        return dict(self._providers)

    def _publish_failure(self, alert: Alert, result: dict[str, Any]) -> None:
        logger.warning("Alert notification delivery failed: %s", result)
        get_event_bus().publish(
            EventType.ALERT_EVENT,
            alert.to_dict(),
            source="notification_dispatcher",
            priority=3,
            metadata={"delivery_failure": result},
        )


def _safe_provider_config() -> dict:
    try:
        return load_runtime_config("notification_providers")
    except FileNotFoundError as exc:
        logger.warning("Notification provider config unavailable; using disabled defaults: %s", exc)
        return {}
