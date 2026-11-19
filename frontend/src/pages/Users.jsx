/**
 * FraudShield AI - Admin > Users page (Week 12 Day 6)
 * =======================================================
 */
import { useEffect, useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

const ROLES = ['admin', 'analyst', 'user']

const errorOf = (err, fallback) => err.response?.data?.error?.message || fallback

export default function Users() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ email: '', password: '', role: 'user' })
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    try {
      const { data } = await api.get('/users')
      setUsers(data)
    } catch (err) {
      setError(errorOf(err, 'Could not load users.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Every action reports success or the server's reason for refusing, instead of failing silently.
  async function run(fn, success, fallback) {
    setError(null); setNotice(null)
    try { await fn(); setNotice(success); await load() } catch (err) { setError(errorOf(err, fallback)); await load() }
  }

  async function createUser(e) {
    e.preventDefault()
    setSaving(true)
    await run(async () => { await api.post('/users', form); setForm({ email: '', password: '', role: 'user' }) },
      `Created ${form.email}.`, 'Failed to create user.')
    setSaving(false)
  }

  const changeRole = (u, role) => run(() => api.patch(`/users/${u.id}/role`, { role }), `${u.email} is now ${role}.`, 'Could not change the role.')
  const removeUser = (u) => {
    if (!window.confirm(`Delete ${u.email}? This cannot be undone.`)) return
    return run(() => api.delete(`/users/${u.id}`), `Deleted ${u.email}.`, 'Could not delete the user.')
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-lg font-bold text-white">User Management</h1>

      <form onSubmit={createUser} className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-slate-500 block mb-1">Email</label>
          <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white" />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Password</label>
          <input required type="password" minLength={8} autoComplete="new-password" placeholder="8+ characters" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white" />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Role</label>
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white">
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <button type="submit" disabled={saving} className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg px-4 py-1.5">
          {saving ? 'Creating…' : 'Create User'}
        </button>
      </form>
      {error && <div role="alert" className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">{error}</div>}
      {notice && !error && <div role="status" className="text-sm text-emerald-300 bg-emerald-950/30 border border-emerald-900 rounded-lg px-3 py-2">{notice}</div>}

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 bg-slate-950/50">
              <th className="py-2 px-4">Email</th><th className="px-4">Role</th><th className="px-4">Created</th><th className="px-4"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const self = u.id === me?.id
              return (
              <tr key={u.id} className="border-t border-slate-800">
                <td className="py-2 px-4">{u.email}{self && <span className="ml-2 text-xs rounded bg-indigo-950 text-indigo-300 px-1.5 py-0.5">You</span>}</td>
                <td className="px-4">
                  <select value={u.role} disabled={self} title={self ? 'You cannot change your own role' : undefined} onChange={(e) => changeRole(u, e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white disabled:opacity-50">
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 text-slate-500">{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="px-4">
                  {!self && <button onClick={() => removeUser(u)} className="text-xs text-red-400 hover:underline">Delete</button>}
                </td>
              </tr>
              )
            })}
            {!loading && users.length === 0 && (
              <tr><td colSpan={4} className="py-6 px-4 text-center text-slate-500">No users yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
