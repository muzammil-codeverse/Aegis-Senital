# Camera Geospatial Model (Phase 42)

## Camera geo profile

Each camera may have a **CameraGeoProfile** with:

- WGS84 `latitude` / `longitude` (validated bounds)
- Optional `altitude_meters`
- `heading_degrees` (0–360) for horizontal orientation
- `fov_degrees` and `coverage_radius_meters` defining **camera coverage** on the map
- Optional `floor_level`, `region`, and non-sensitive `metadata`

## Field-of-view (FOV) cone (2D map projection)

For map display, FOV is modeled as a **deterministic wedge polygon**: the camera position plus an arc of sample points at `coverage_radius_meters` between `heading ± fov/2`. This is a **planning / visualization aid**, not a legal survey.

## Event placement rule

**Event markers** derive their coordinates from the **authorized camera geo profile** when the event is tied to a camera. **Uploaded video** sessions may supply **demo** coordinates in session metadata (`demo_latitude` / `demo_longitude`) or fall back to a **linked camera** profile when the operator has access.

## Safe wording

Copy uses **possible incident**, **operator review required**, and avoids guilt or identity confirmation language on the map surface.
