export default function CameraMarkerLayer({ cameras, project, onSelect }) {
  return (
    <>
      {(cameras || []).map(cam => {
        const pos = project(cam.latitude, cam.longitude)
        return (
          <button
            key={cam.camera_id}
            type="button"
            title={cam.name || cam.camera_id}
            className="gis-marker gis-marker-camera"
            style={{ position: 'absolute', ...pos, transform: 'translate(-50%,-50%)', zIndex: 3 }}
            onClick={() => onSelect?.(cam.camera_id)}
          >
            <span className="gis-marker-dot" />
          </button>
        )
      })}
    </>
  )
}
