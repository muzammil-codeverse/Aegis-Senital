export default function AccessDenied({ permission }) {
  return (
    <section className="panel access-denied">
      <div>
        <p className="eyebrow">Access Control</p>
        <h2>Access denied</h2>
      </div>
      <p className="muted">
        Your current role does not include {permission || 'the required'} permission.
      </p>
    </section>
  )
}
