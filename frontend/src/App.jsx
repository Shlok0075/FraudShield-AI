import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import NavBar from './components/NavBar'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Alerts from './pages/Alerts'
import TransactionDetail from './pages/TransactionDetail'
import AuditLog from './pages/AuditLog'
import Users from './pages/Users'
import Cases from './pages/Cases'
import Intelligence from './pages/Intelligence'

function AppLayout({ children }) {
  const { isAuthenticated } = useAuth()
  return (
    <div className="min-h-screen bg-slate-950">
      {isAuthenticated && <NavBar />}
      {children}
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppLayout>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
            <Route path="/cases" element={<ProtectedRoute roles={['admin','analyst']}><Cases /></ProtectedRoute>} />
            <Route path="/intelligence" element={<ProtectedRoute roles={['admin','analyst']}><Intelligence /></ProtectedRoute>} />
            <Route path="/transactions/:id" element={<ProtectedRoute><TransactionDetail /></ProtectedRoute>} />
            <Route path="/audit" element={<ProtectedRoute roles={['admin']}><AuditLog /></ProtectedRoute>} />
            <Route path="/users" element={<ProtectedRoute roles={['admin']}><Users /></ProtectedRoute>} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </AuthProvider>
  )
}
