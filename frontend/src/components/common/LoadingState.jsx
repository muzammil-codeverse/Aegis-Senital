export default function LoadingState({ label = 'Loading data' }) {
  return (
    <div className="state state-loading" role="status">
      <span className="pulse-dot" />
      <span>{label}</span>
    </div>
  )
}
