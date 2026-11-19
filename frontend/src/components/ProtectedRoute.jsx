import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, roles }) {
  const { isAuthenticated, user, restoring } = useAuth()
  const location = useLocation()

  if (restoring) {
    return <div className="p-8 text-center text-slate-500">Restoring your session…</div>
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="p-8 text-center text-slate-400">
        You don't have permission to view this page (requires: {roles.join(', ')}).
      </div>
    )
  }
  return children
}
