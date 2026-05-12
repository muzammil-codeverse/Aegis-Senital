export default function CameraFovLayer({ fovs, project }) {
  return (
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} viewBox="0 0 100 100" preserveAspectRatio="none">
      {(fovs || []).map(fov => {
        const pts = (fov.polygon || [])
          .map(p => {
            const pos = project(p.latitude, p.longitude)
            const x = parseFloat(String(pos.left).replace('%', ''))
            const y = parseFloat(String(pos.top).replace('%', ''))
            return `${x},${y}`
          })
          .join(' ')
        return <polygon key={fov.camera_id} points={pts} fill="rgba(96,165,250,0.1)" stroke="rgba(96,165,250,0.5)" strokeWidth="0.2" />
      })}
    </svg>
  )
}
