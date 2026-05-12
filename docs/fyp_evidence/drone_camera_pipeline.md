# Drone Camera Pipeline

## Frame Path

1. Cosys-AirSim RPC returns the `front_center` RGB image for `Drone1`.
2. `CosysAirSimClient.get_frame()` converts the response into a JPEG-backed `DroneCameraFrame`.
3. `DroneFrameAdapter` decodes the base64 image into a numpy frame and emits a `DecodedFramePacket`.
4. The packet is passed to `StreamProcessor.process_decoded_packet()` so the same governed inference path is used as live streams.
5. Resulting detections, anomaly events, and incident metadata continue through the existing event and persistence pipeline.

## Required Metadata

Every adapted packet includes:

- `source_type: drone_simulation`
- `camera_id: drone_sim_01`
- `drone_id: drone_sim_01`
- `simulated: true`
- `telemetry`
- `frame_index`
- `timestamp`

## Safety and Governance

- The drone adapter does not create a toy inference branch.
- Existing model governance remains in force because the packet enters the normal `StreamProcessor`.
- Event metadata persists the `drone_simulation` source type and simulated safe label.

## Failure Handling

- If the simulator is not reachable, the client returns `disconnected`.
- If a frame cannot be captured, the frame response is `degraded` or `disconnected` with a clear error.
- No fallback frame or invented telemetry is emitted.
