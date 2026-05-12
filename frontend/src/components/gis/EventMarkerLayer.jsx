export default function EventMarkerLayer({ markers, project, onSelect }) {
  return (
    <>
      {(markers || []).map(ev => {
        const pos = project(ev.latitude, ev.longitude)
        return (
          <button
            key={`${ev.event_id}-${ev.source_type}`}
            type="button"
            className="gis-marker gis-marker-event"
            style={{ position: 'absolute', ...pos, transform: 'translate(-50%,-50%)', zIndex: 2 }}
            title={ev.title || 'Possible incident'}
            onClick={() => onSelect?.(ev)}
          >
            <span className="gis-marker-pulse" />
          </button>
        )
      })}
    </>
  )
}
