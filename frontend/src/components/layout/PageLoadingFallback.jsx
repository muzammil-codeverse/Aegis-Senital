/**
 * PageLoadingFallback — displayed by Suspense while a lazy page chunk is loading.
 * Provides a minimal, accessible loading indicator with an ARIA status role.
 *
 * @param {string} label  Human-readable loading label shown to the user.
 */
export default function PageLoadingFallback({ label = 'Loading...' }) {
  return (
    <div className="page-loading-fallback" role="status" aria-label={label}>
      <div className="page-loading-fallback__inner">
        <span className="pulse-dot" />
        <span>{label}</span>
      </div>
    </div>
  )
}
