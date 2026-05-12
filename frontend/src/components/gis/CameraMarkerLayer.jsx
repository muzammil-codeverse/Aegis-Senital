export default function CameraMarkerLayer({ cameras, project, onSelect }) {
  return (
    <>
      {(cameras || []).map(cam => {
        const pos = project(cam.latitude, cam.longitude)
        const isDrone = cam?.metadata?.source_type === 'drone_simulation' || cam?.camera_id === 'drone_sim_01'
        return (
          <button
            key={cam.camera_id}
            type="button"
            title={`${cam.name || cam.camera_id}${isDrone ? ' - simulated drone feed' : ''}`}
            className={`gis-marker ${isDrone ? 'gis-marker-drone' : 'gis-marker-camera'}`}
            style={{ position: 'absolute', ...pos, transform: 'translate(-50%,-50%)', zIndex: 3 }}
            onClick={() => onSelect?.(cam.camera_id)}
          >
            <span
              className="gis-marker-dot"
              style={isDrone ? { background: '#f59e0b', boxShadow: '0 0 0 3px rgba(245, 158, 11, 0.25)' } : undefined}
            />
          </button>
        )
      })}
    </>
  )
}
