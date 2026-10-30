import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const linkClass = ({ isActive }) =>
  `px-3 py-2 rounded-lg text-sm font-medium ${isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'}`

export default function NavBar() {
  const { user, logout } = useAuth()

  return (
    <nav className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950">
      <div className="flex items-center gap-6">
        <span className="text-lg font-bold text-white">🛡️ FraudShield AI</span>
        <NavLink to="/dashboard" className={linkClass}>Dashboard</NavLink>
        <NavLink to="/alerts" className={linkClass}>Alerts</NavLink>
        {(user?.role === 'admin' || user?.role === 'analyst') && <NavLink to="/cases" className={linkClass}>Cases</NavLink>}
        {(user?.role === 'admin' || user?.role === 'analyst') && <NavLink to="/intelligence" className={linkClass}>Intelligence</NavLink>}
        <NavLink to="/audit" className={linkClass}>Audit Log</NavLink>
        {user?.role === 'admin' && (
          <NavLink to="/users" className={linkClass}>Users</NavLink>
        )}
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-slate-400">{user?.email} · <span className="uppercase text-xs">{user?.role}</span></span>
        <button
          onClick={logout}
          className="px-3 py-1.5 rounded-lg text-sm bg-slate-800 hover:bg-slate-700 text-slate-200"
        >
          Logout
        </button>
      </div>
    </nav>
  )
}
