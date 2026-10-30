import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, roles }) {
  const { isAuthenticated, user } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
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
