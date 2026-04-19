import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Journal from './pages/Journal'
import Analytics from './pages/Analytics'
import Orders from './pages/Orders'
import Trades from './pages/Trades'
import Backtest from './pages/Backtest'
import Settings from './pages/Settings'
import { authApi } from './api'
import { useStore } from './store'

export default function App() {
  const setAuthStatus = useStore((s) => s.setAuthStatus)

  useEffect(() => {
    // Load saved tokens on app start
    authApi.loadTokens().catch(() => {})
    // Check auth status
    authApi.status().then((r) => {
      setAuthStatus({
        codex: r.data.codex_connected,
        deepseek: r.data.deepseek_configured,
        bybit: r.data.bybit_configured,
      })
    }).catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="journal" element={<Journal />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="orders" element={<Orders />} />
          <Route path="trades" element={<Trades />} />
          <Route path="backtest" element={<Backtest />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
