import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type TradingMode = 'real' | 'paper' | 'backtest'

interface VoltageStore {
  // Current active mode (global switch)
  mode: TradingMode
  setMode: (m: TradingMode) => void

  // Engine status
  engineRunning: { real: boolean; paper: boolean; backtest: boolean }
  setEngineRunning: (mode: TradingMode, running: boolean) => void

  // WebSocket
  wsConnected: boolean
  setWsConnected: (v: boolean) => void

  // Selected symbol for chart/analysis
  selectedSymbol: string
  setSelectedSymbol: (s: string) => void

  // Selected market type
  selectedMarket: 'spot' | 'futures'
  setSelectedMarket: (m: 'spot' | 'futures') => void

  // Live PnL for header display
  livePnl: { unrealized: number; today: number }
  setLivePnl: (p: { unrealized: number; today: number }) => void

  // Auth
  codexConnected: boolean
  deepseekConfigured: boolean
  bybitConfigured: boolean
  setAuthStatus: (s: { codex: boolean; deepseek: boolean; bybit: boolean }) => void
}

export const useStore = create<VoltageStore>()(
  persist(
    (set) => ({
      mode: 'paper',
      setMode: (mode) => set({ mode }),

      engineRunning: { real: false, paper: false, backtest: false },
      setEngineRunning: (mode, running) =>
        set((s) => ({ engineRunning: { ...s.engineRunning, [mode]: running } })),

      wsConnected: false,
      setWsConnected: (wsConnected) => set({ wsConnected }),

      selectedSymbol: 'BTCUSDT',
      setSelectedSymbol: (selectedSymbol) => set({ selectedSymbol }),

      selectedMarket: 'spot',
      setSelectedMarket: (selectedMarket) => set({ selectedMarket }),

      livePnl: { unrealized: 0, today: 0 },
      setLivePnl: (livePnl) => set({ livePnl }),

      codexConnected: false,
      deepseekConfigured: false,
      bybitConfigured: false,
      setAuthStatus: ({ codex, deepseek, bybit }) =>
        set({ codexConnected: codex, deepseekConfigured: deepseek, bybitConfigured: bybit }),
    }),
    { name: 'voltage-store', partialize: (s) => ({ mode: s.mode, selectedSymbol: s.selectedSymbol, selectedMarket: s.selectedMarket }) }
  )
)
