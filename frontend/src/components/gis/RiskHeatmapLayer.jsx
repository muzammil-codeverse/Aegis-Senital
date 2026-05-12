export default function RiskHeatmapLayer({ cells, project }) {
  const max = Math.max(...(cells || []).map(c => c.weight), 1)
  return (
    <>
      {(cells || []).map(cell => {
        const pos = project(cell.center_latitude, cell.center_longitude)
        const alpha = 0.15 + 0.55 * (cell.weight / max)
        return (
          <div
            key={cell.cell_id}
            style={{
              position: 'absolute',
              ...pos,
              transform: 'translate(-50%,-50%)',
              width: 36,
              height: 36,
              borderRadius: '50%',
              background: `rgba(255, 94, 58, ${alpha})`,
              pointerEvents: 'none',
            }}
          />
        )
      })}
    </>
  )
}
