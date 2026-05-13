export default function ErrorState({ message = 'Runtime data temporarily unavailable', onRetry }) {
  return (
    <div className="state state-error" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="text-button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}
