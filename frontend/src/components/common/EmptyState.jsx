export default function EmptyState({ message = 'No live data available' }) {
  return <div className="state state-empty">{message}</div>
}
