from __future__ import annotations

import logging
import math
import threading
import time

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        return load_runtime_config("geospatial")
    except Exception:
        return {}


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm for 2-D point-in-polygon."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class GeospatialService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cfg: dict | None = None

    def _get_cfg(self) -> dict:
        with self._lock:
            if self._cfg is None:
                self._cfg = _load_config()
            return self._cfg

    def reload(self) -> None:
        with self._lock:
            self._cfg = _load_config()

    # ── sites ─────────────────────────────────────────────────────────────────

    def list_sites(self) -> list[dict]:
        from app.models.geospatial_models import MapSite
        cfg = self._get_cfg()
        sites_raw = cfg.get("sites") or []
        return [MapSite.from_dict(s).to_dict() for s in sites_raw]

    def get_site(self, site_id: str | None = None) -> dict | None:
        cfg = self._get_cfg()
        default_id = (cfg.get("map") or {}).get("default_site", "main_site")
        target = site_id or default_id
        sites = self.list_sites()
        for s in sites:
            if s["site_id"] == target:
                return s
        return sites[0] if sites else None

    # ── zones ─────────────────────────────────────────────────────────────────

    def list_zones(self, site_id: str | None = None) -> list[dict]:
        from app.models.geospatial_models import OperationalZone
        cfg = self._get_cfg()
        zones_raw = cfg.get("zones") or []
        return [OperationalZone.from_dict(z).to_dict() for z in zones_raw]

    def get_zone(self, zone_id: str) -> dict | None:
        for z in self.list_zones():
            if z["zone_id"] == zone_id:
                return z
        return None

    # ── geofences (restricted zones) ─────────────────────────────────────────

    def list_geofences(self) -> list[dict]:
        from app.models.geospatial_models import Geofence, OperationalZone
        fences = []
        for z in self.list_zones():
            oz = OperationalZone.from_dict(z)
            if oz.restricted:
                fences.append(Geofence.from_zone(oz).to_dict())
        return fences

    # ── camera nodes ──────────────────────────────────────────────────────────

    def get_camera_nodes(self) -> list[dict]:
        from app.models.geospatial_models import CameraMapNode, GeoPoint
        nodes = []
        try:
            from app.services.camera_registry import get_camera_registry
            cameras = get_camera_registry().list_cameras()
        except Exception:
            cameras = []

        # Latest alert severity per camera
        alert_sev: dict[str, str] = {}
        try:
            from inference.runtime import get_intelligence_runtime
            resp = get_intelligence_runtime().get_alerts(limit=200)
            for a in (resp.get("items") or []):
                for cid in (a.get("camera_ids") or []):
                    cid_s = str(cid)
                    if cid_s not in alert_sev:
                        alert_sev[cid_s] = a.get("severity", "info")
        except Exception:
            pass

        for cam in cameras:
            loc = cam.location or {}
            if isinstance(loc, dict):
                gp = GeoPoint(
                    lat=loc.get("lat"),
                    lng=loc.get("lng"),
                    x=loc.get("x"),
                    y=loc.get("y"),
                    floor=loc.get("floor"),
                )
            else:
                gp = GeoPoint()

            meta = cam.metadata or {}
            fov = cam.fov_degrees if cam.fov_degrees is not None else float(meta.get("fov_degrees") or 90)
            vdir = cam.view_direction_degrees if cam.view_direction_degrees is not None else float(meta.get("view_direction_degrees") or 0)
            crad = cam.coverage_radius if cam.coverage_radius is not None else float(meta.get("coverage_radius") or 150)
            node = CameraMapNode(
                camera_id=cam.camera_id,
                name=cam.name,
                status=cam.status,
                priority=cam.priority,
                location=gp,
                zone=cam.zone,
                fov_degrees=fov,
                view_direction_degrees=vdir,
                coverage_radius=crad,
                latest_alert_severity=alert_sev.get(cam.camera_id),
                latest_frame_url=f"/api/cameras/{cam.camera_id}/latest-frame/image",
                metadata=meta,
            )
            nodes.append(node.to_dict())
        return nodes

    # ── camera connections ────────────────────────────────────────────────────

    def get_camera_connections(self) -> list[dict]:
        from app.models.geospatial_models import CameraConnection
        connections: list[dict] = []

        # From geospatial.yaml
        cfg = self._get_cfg()
        for conn_raw in (cfg.get("connections") or []):
            c = CameraConnection.from_dict(conn_raw)
            connections.append(c.to_dict())
            if c.bidirectional:
                rev = CameraConnection(
                    from_camera=c.to_camera,
                    to_camera=c.from_camera,
                    distance_meters=c.distance_meters,
                    min_travel_seconds=c.min_travel_seconds,
                    max_travel_seconds=c.max_travel_seconds,
                    transition_probability=c.transition_probability,
                    bidirectional=False,
                    metadata={"auto_reversed": True},
                )
                connections.append(rev.to_dict())

        # Also merge from camera_graph.yaml if it uses our camera ids
        seen = {(c["from_camera"], c["to_camera"]) for c in connections}
        try:
            from inference.config_runtime import load_runtime_config
            graph_cfg = load_runtime_config("camera_graph")
            for conn_raw in (graph_cfg.get("connections") or []):
                fc = str(conn_raw.get("from", ""))
                tc = str(conn_raw.get("to", ""))
                if (fc, tc) not in seen:
                    c = CameraConnection(
                        from_camera=fc,
                        to_camera=tc,
                        distance_meters=float(conn_raw.get("distance_meters", 0)),
                        min_travel_seconds=float(conn_raw.get("min_travel_seconds", 0)),
                        max_travel_seconds=float(conn_raw.get("max_travel_seconds", 60)),
                        transition_probability=float(conn_raw.get("transition_probability", 0.5)),
                    )
                    connections.append(c.to_dict())
                    seen.add((fc, tc))
        except Exception:
            pass

        return connections

    # ── incident markers ──────────────────────────────────────────────────────

    def get_incident_markers(self) -> list[dict]:
        from app.models.geospatial_models import MapIncidentMarker, GeoPoint
        markers: list[dict] = []
        try:
            from inference.runtime import get_intelligence_runtime
            incidents = get_intelligence_runtime().get_incidents()
        except Exception:
            return markers

        nodes_by_id = {n["camera_id"]: n for n in self.get_camera_nodes()}

        for inc in (incidents or []):
            if isinstance(inc, dict):
                inc_id = inc.get("incident_id") or inc.get("id", "")
                inc_type = inc.get("incident_type") or inc.get("type", "unknown")
                severity = inc.get("severity", "medium")
                timestamp = inc.get("started_at") or inc.get("created_at")
                status = inc.get("status", "active")
                camera_ids = inc.get("camera_ids") or []
            else:
                inc_id = getattr(inc, "incident_id", "") or getattr(inc, "id", "")
                inc_type = getattr(inc, "incident_type", "unknown")
                severity = getattr(inc, "severity", "medium")
                timestamp = getattr(inc, "started_at", None) or getattr(inc, "created_at", None)
                status = getattr(inc, "status", "active")
                camera_ids = getattr(inc, "camera_ids", []) or []

            if not inc_id:
                continue

            # Determine location from first camera
            cam_id = camera_ids[0] if camera_ids else None
            node = nodes_by_id.get(cam_id) if cam_id else None
            loc = GeoPoint()
            if node:
                node_loc = node.get("location") or {}
                loc = GeoPoint(
                    x=node_loc.get("x"),
                    y=node_loc.get("y"),
                    lat=node_loc.get("lat"),
                    lng=node_loc.get("lng"),
                )

            marker = MapIncidentMarker(
                incident_id=str(inc_id),
                incident_type=str(inc_type),
                severity=str(severity),
                location=loc,
                camera_id=cam_id,
                timestamp=float(timestamp) if timestamp else None,
                status=str(status),
            )
            markers.append(marker.to_dict())
        return markers

    # ── alert markers ─────────────────────────────────────────────────────────

    def get_alert_markers(self) -> list[dict]:
        from app.models.geospatial_models import MapAlertMarker, GeoPoint
        markers: list[dict] = []
        try:
            from inference.runtime import get_intelligence_runtime
            resp = get_intelligence_runtime().get_live_alert_feed(limit=100)
            alerts = resp.get("items") or []
        except Exception:
            return markers

        nodes_by_id = {n["camera_id"]: n for n in self.get_camera_nodes()}

        for alert in alerts:
            if isinstance(alert, dict):
                alert_id = alert.get("alert_id", "")
                title = alert.get("title", "")
                severity = alert.get("severity", "medium")
                timestamp = alert.get("created_at") or alert.get("updated_at")
                state = alert.get("state", "active")
                camera_ids = alert.get("camera_ids") or []
            else:
                alert_id = getattr(alert, "alert_id", "")
                title = getattr(alert, "title", "")
                severity = getattr(alert, "severity", "medium")
                timestamp = getattr(alert, "created_at", None)
                state = getattr(alert, "state", "active")
                camera_ids = getattr(alert, "camera_ids", []) or []

            if not alert_id:
                continue

            cam_id = camera_ids[0] if camera_ids else None
            node = nodes_by_id.get(cam_id) if cam_id else None
            loc = GeoPoint()
            if node:
                node_loc = node.get("location") or {}
                loc = GeoPoint(
                    x=node_loc.get("x"),
                    y=node_loc.get("y"),
                    lat=node_loc.get("lat"),
                    lng=node_loc.get("lng"),
                )

            marker = MapAlertMarker(
                alert_id=str(alert_id),
                title=str(title),
                severity=str(severity),
                location=loc,
                camera_id=cam_id,
                timestamp=float(timestamp) if timestamp else None,
                state=str(state),
            )
            markers.append(marker.to_dict())
        return markers

    # ── map state ─────────────────────────────────────────────────────────────

    def get_map_state(self) -> dict:
        site = self.get_site()
        return {
            "site": site,
            "zones": self.list_zones(),
            "geofences": self.list_geofences(),
            "cameras": self.get_camera_nodes(),
            "connections": self.get_camera_connections(),
            "incidents": self.get_incident_markers(),
            "alerts": self.get_alert_markers(),
            "generated_at": time.time(),
        }

    # ── topology ──────────────────────────────────────────────────────────────

    def get_camera_topology(self) -> dict:
        cameras = self.get_camera_nodes()
        connections = self.get_camera_connections()
        adjacency: dict[str, list[str]] = {c["camera_id"]: [] for c in cameras}
        for conn in connections:
            fc = conn["from_camera"]
            tc = conn["to_camera"]
            if fc in adjacency:
                adjacency[fc].append(tc)
        return {
            "cameras": cameras,
            "connections": connections,
            "adjacency": adjacency,
        }

    # ── point in zone ─────────────────────────────────────────────────────────

    def point_in_zone(self, point: dict, zone_id: str) -> bool:
        zone = self.get_zone(zone_id)
        if zone is None:
            return False
        x = float(point.get("x") or 0)
        y = float(point.get("y") or 0)
        return _point_in_polygon(x, y, zone["polygon"])

    # ── event engine adapter ──────────────────────────────────────────────────

    def get_event_engine_restricted_zones(self) -> list[dict]:
        """
        Convert restricted OperationalZones to the shape EventEngine expects:
        {"zone": [[x,y], ...], "zone_id": str, "name": str, ...}
        """
        result = []
        for z in self.list_zones():
            if z.get("restricted"):
                result.append({
                    "zone": z["polygon"],
                    "zone_id": z["zone_id"],
                    "name": z["name"],
                    "allowed_objects": z.get("allowed_objects") or [],
                    "active_hours": z.get("active_hours") or [0, 24],
                })
        return result


_geo_service: GeospatialService | None = None
_geo_service_lock = threading.Lock()


def get_geospatial_service() -> GeospatialService:
    global _geo_service
    if _geo_service is None:
        with _geo_service_lock:
            if _geo_service is None:
                _geo_service = GeospatialService()
    return _geo_service
