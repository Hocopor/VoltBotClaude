import axios from 'axios'
import toast from 'react-hot-toast'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
      return Promise.reject(err)
    }
    const msg = err.response?.data?.detail || err.message || 'Request failed'
    toast.error(msg)
    return Promise.reject(err)
  }
)

// ─── AUTH ──────────────────────────────────────────────────
export const authApi = {
  session:          () => api.get('/auth/session'),
  login:            (d: { login: string; password: string }) => api.post('/auth/login', d),
  logout:           () => api.post('/auth/logout'),
  status:           () => api.get('/auth/status'),
  codexLoginUrl:    () => api.get('/auth/codex/login'),
  codexDisconnect:  () => api.delete('/auth/codex/disconnect'),
  saveApiKeys:      (d: any) => api.post('/auth/apikeys', d),
  loadTokens:       () => api.post('/auth/load-tokens'),
}

// ─── MARKET ────────────────────────────────────────────────
export const marketApi = {
  spotPairs:    () => api.get('/market/pairs/spot'),
  futuresPairs: () => api.get('/market/pairs/futures'),
  klines:       (sym: string, interval: string, cat: string, limit = 200) =>
    api.get(`/market/klines/${sym}`, { params: { interval, category: cat, limit } }),
  orderbook:    (sym: string, cat: string) =>
    api.get(`/market/orderbook/${sym}`, { params: { category: cat } }),
  ticker:       (sym: string, cat: string) =>
    api.get(`/market/ticker/${sym}`, { params: { category: cat } }),
  fearGreed:    () => api.get('/market/fear-greed'),
}

// ─── TRADING ───────────────────────────────────────────────
export const tradingApi = {
  startEngine:    (mode: string) => api.post('/trading/engine', { mode, action: 'start' }),
  stopEngine:     (mode: string) => api.post('/trading/engine', { mode, action: 'stop' }),
  engineStatus:   () => api.get('/trading/engine/status'),
  balance:        (mode: string) => api.get(`/trading/balance/${mode}`),
  openPositions:  (mode: string) => api.get(`/trading/open-positions/${mode}`),
  pnlSummary:     (mode: string) => api.get(`/trading/pnl-summary/${mode}`),
  manualTrade:    (mode: string, d: any) => api.post('/trading/manual-trade', d, { params: { mode } }),
  closeTrade:     (id: number, mode: string) => api.post(`/trading/close/${id}`, {}, { params: { mode } }),
}

// ─── ORDERS ────────────────────────────────────────────────
export const ordersApi = {
  list: (params: Record<string, any>) => api.get('/orders/', { params }),
}

// ─── TRADES ────────────────────────────────────────────────
export const tradesApi = {
  list:  (params: Record<string, any>) => api.get('/trades/', { params }),
  get:   (id: number) => api.get(`/trades/${id}`),
}

// ─── JOURNAL ───────────────────────────────────────────────
export const journalApi = {
  list:       (params: Record<string, any>) => api.get('/journal/', { params }),
  entry:      (id: number) => api.get(`/journal/entry/${id}`),
  byTrade:    (tradeId: number) => api.get(`/journal/by-trade/${tradeId}`),
  updateNotes:(id: number, d: any) => api.patch(`/journal/entry/${id}/notes`, d),
  analyze:    (id: number) => api.post(`/journal/entry/${id}/analyze`),
  dailyPnl:   (mode: string) => api.get('/journal/pnl/daily', { params: { mode } }),
  monthlyPnl: (mode: string) => api.get('/journal/pnl/monthly', { params: { mode } }),
  clear:      (mode: string) => api.delete(`/journal/clear/${mode}`),
}

// ─── ANALYTICS ─────────────────────────────────────────────
export const analyticsApi = {
  overview:        (mode: string) => api.get(`/analytics/overview/${mode}`),
  equityCurve:     (mode: string) => api.get(`/analytics/equity-curve/${mode}`),
  heatmap:         (mode: string) => api.get(`/analytics/heatmap/${mode}`),
  voltageFilters:  (mode: string) => api.get(`/analytics/voltage-filters/${mode}`),
}

// ─── SETTINGS ──────────────────────────────────────────────
export const settingsApi = {
  get:    (mode: string) => api.get(`/settings/${mode}`),
  update: (mode: string, d: any) => api.patch(`/settings/${mode}`, d),
}

// ─── BACKTEST ──────────────────────────────────────────────
export const backtestApi = {
  start:       (d: any) => api.post('/backtest/start', d),
  sessions:    () => api.get('/backtest/sessions'),
  session:     (id: number) => api.get(`/backtest/sessions/${id}`),
  stop:        (id: number) => api.post(`/backtest/sessions/${id}/stop`),
  delete:      (id: number) => api.delete(`/backtest/sessions/${id}`),
  clearAll:    () => api.delete('/backtest/clear-all'),
}

export default api
