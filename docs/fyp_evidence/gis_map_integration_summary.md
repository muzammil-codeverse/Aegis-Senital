# GIS Map Integration Summary (Phase 42)

## What GIS means in Aegis Sentinel

Geographic information systems (GIS) in Aegis Sentinel provide a **map-based situational layer** for **camera coverage**, **candidate event locations**, **cases**, **risk heatmaps**, and **geofences (restricted / patrol / safe / high-risk zones)**. Language stays non-confirmatory: **possible incident**, **operator review required**, **risk zone**, **candidate event location**.

## Scope delivered

- Runtime configuration: `configs/runtime/gis.yaml`
- Backend models, repository (JSONL dev), service (FOV, distance, heatmap, geofence checks), and secured REST APIs under `/api/gis/*`
- Frontend **Map** page (`#map-operations`) with **local_mock** map plane (no paid API key required) and optional **Mapbox** when `VITE_MAPBOX_TOKEN` is set
- Metrics counters (`gis_*`) and runtime health `checks.gis`
- Demo seed script: `scripts/seed_demo_gis_profiles.py`

## Privacy and access control

- **Phase 35 object authorization** is enforced: camera geo reads require camera scope; markers are filtered by incident/case/uploaded-video rules.
- Unauthorized camera coordinates are **not listed** for scoped users.

## Carry-forward (Phase 43+)

- **Phase 43 — Investigative path reconstruction**: consume ordered timeline + map geometry (FOV, corridors) for route hypotheses.
- **Phase 44–45 — Drone simulation / patrol**: reuse geofences, heatmap cells, and `drone_simulation` source type on the map.
- **Phase 48 — 3D command interface**: optional Three.js / R3F layers; dependencies are installed for future phases.
