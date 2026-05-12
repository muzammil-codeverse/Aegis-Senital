# Geofence and Heatmap Design (Phase 42)

## Geofences (restricted zones)

Geofences are stored as JSONL in development (`storage/gis/geofences.jsonl`) with a **polygon** (ordered `GeoPoint` vertices), `zone_type` (`restricted | patrol | safe | high_risk`), `severity`, and `active` flag. **Point-in-polygon** checks use Shapely for membership tests in the service layer.

Production configuration anticipates PostgreSQL-backed storage (`geofencing.production_backend`) while keeping the same API contract.

## Risk heatmap

Heatmap cells aggregate **event markers** that passed object authorization. Each marker contributes a **severity weight** from `configs/runtime/gis.yaml`:

- low / medium / high / critical → configurable integer weights

Cells are keyed by quantized latitude/longitude bins derived from `heatmap.radius_meters`. The result is a **relative risk concentration** layer for supervisors, not a verdict.

## Network graph placeholder

Heatmap aggregation optionally constructs a **NetworkX** graph over cell IDs to reserve integration points for **Phase 43 path reconstruction** without changing the anomaly engine in Phase 42.

## Access control

Geofence CRUD requires `gis:write`. Map reads require `gis:read`. Camera-specific reads additionally require **camera object access**.
