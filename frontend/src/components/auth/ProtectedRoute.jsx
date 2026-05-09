import { useAuth } from '../../hooks/useAuth'
import AccessDenied from './AccessDenied'

export default function ProtectedRoute({ permission, children }) {
  const { hasPermission } = useAuth()
  if (!hasPermission(permission)) return <AccessDenied permission={permission} />
  return children
}
