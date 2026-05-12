/**
 * PermissionDeniedState — shown when the authenticated user lacks the permission
 * required to view a protected page or section.
 *
 * @param {string} [permission]  The permission key that was required (optional, for display).
 */
export default function PermissionDeniedState({ permission }) {
  return (
    <div className="state state-permission-denied" role="alert">
      <p className="eyebrow">Access restricted</p>
      <p>You do not have permission to view this section.</p>
      {permission && <p className="muted">Required: {permission}</p>}
    </div>
  )
}
