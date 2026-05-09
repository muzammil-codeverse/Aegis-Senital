import { useAuth } from '../../hooks/useAuth'

export default function PermissionGate({ permission, children, fallback = null }) {
  const { hasPermission } = useAuth()
  if (!hasPermission(permission)) return fallback
  return children
}
