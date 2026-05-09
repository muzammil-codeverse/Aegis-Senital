export default function RoleBadge({ role }) {
  const label = role || 'unknown'
  return <span className={`role-badge role-${label}`}>{label}</span>
}
