import { useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import ChangePasswordModal from './ChangePasswordModal'
import RoleBadge from './RoleBadge'

export default function UserMenu() {
  const { user, logout } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  if (!user) return null
  return (
    <>
      <div className="user-menu">
        <div className="user-menu-id">
          <span>{user.display_name || user.username}</span>
          <RoleBadge role={user.role} />
        </div>
        <button type="button" className="text-button" onClick={() => setChangingPassword(true)}>
          Password
        </button>
        <button type="button" className="text-button" onClick={logout}>
          Logout
        </button>
      </div>
      <ChangePasswordModal open={changingPassword} onClose={() => setChangingPassword(false)} />
    </>
  )
}
