/**
 * FraudShield AI - Admin > Users page (Week 12 Day 6)
 * =======================================================
 */
import { useEffect, useState } from 'react'
import api from '../services/api'

const ROLES = ['admin', 'analyst', 'user']

export default function Users() {
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ email: '', password: '', role: 'user' })
  const [error, setError] = useState(null)

  async function load() {
    const { data } = await api.get('/users')
    setUsers(data)
  }

  useEffect(() => { load() }, [])

  async function createUser(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.post('/users', form)
      setForm({ email: '', password: '', role: 'user' })
      load()
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Failed to create user')
    }
  }

  async function changeRole(id, role) {
    await api.patch(`/users/${id}/role`, { role })
    load()
  }

  async function removeUser(id) {
    await api.delete(`/users/${id}`)
    load()
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
          <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white" />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Role</label>
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white">
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg px-4 py-1.5">
          Create User
        </button>
      </form>
      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 bg-slate-950/50">
              <th className="py-2 px-4">Email</th><th className="px-4">Role</th><th className="px-4">Created</th><th className="px-4"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-slate-800">
                <td className="py-2 px-4">{u.email}</td>
                <td className="px-4">
                  <select value={u.role} onChange={(e) => changeRole(u.id, e.target.value)}
                    className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white">
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 text-slate-500">{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="px-4">
                  <button onClick={() => removeUser(u.id)} className="text-xs text-red-400 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
