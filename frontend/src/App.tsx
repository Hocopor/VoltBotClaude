import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Journal from './pages/Journal'
import Analytics from './pages/Analytics'
import Orders from './pages/Orders'
import Trades from './pages/Trades'
import Backtest from './pages/Backtest'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { authApi } from './api'
import { useStore } from './store'

export default function App() {
  const authenticated = useStore((s) => s.authenticated)
  const setAppSession = useStore((s) => s.setAppSession)
  const clearAppSession = useStore((s) => s.clearAppSession)
  const setAuthStatus = useStore((s) => s.setAuthStatus)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    authApi.session()
      .then((r) => {
        if (r.data.authenticated) {
          setAppSession({ authenticated: true, login: r.data.login })
          return authApi.loadTokens()
            .catch(() => {})
            .then(() => authApi.status())
            .then((status) => {
              setAuthStatus({
                codex: status.data.codex_connected,
                deepseek: status.data.deepseek_configured,
                bybit: status.data.bybit_configured,
              })
            })
        }
        clearAppSession()
        return null
      })
      .catch(() => {
        clearAppSession()
      })
      .finally(() => setCheckingSession(false))
  }, [])

  if (checkingSession) {
    return <div className="min-h-screen bg-voltage-bg flex items-center justify-center text-voltage-muted">Checking session...</div>
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={authenticated ? <Navigate to="/" replace /> : <Login />} />
        <Route
          path="/"
          element={authenticated ? <Layout /> : <Navigate to="/login" replace />}
        >
          <Route index element={<Dashboard />} />
          <Route path="journal" element={<Journal />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="orders" element={<Orders />} />
          <Route path="trades" element={<Trades />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to={authenticated ? "/" : "/login"} replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
