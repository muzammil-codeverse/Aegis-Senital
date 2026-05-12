export default function CaseMarkerLayer({ markers, project }) {
  return (
    <>
      {(markers || []).map(c => {
        const pos = project(c.latitude, c.longitude)
        return (
          <div
            key={c.case_id}
            className="gis-marker gis-marker-case"
            style={{ position: 'absolute', ...pos, transform: 'translate(-50%,-50%)' }}
            title={c.title}
          >
            <span className="gis-marker-square" />
          </div>
        )
      })}
    </>
  )
}
