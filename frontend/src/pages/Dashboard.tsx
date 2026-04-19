import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Play, Square, RefreshCw } from 'lucide-react'
import { tradingApi, marketApi } from '../api'
import { useStore } from '../store'
import TradingChart from '../components/charts/TradingChart'
import PositionsTable from '../components/dashboard/PositionsTable'
import AISignalPanel from '../components/dashboard/AISignalPanel'
import BalancePanel from '../components/dashboard/BalancePanel'
import FearGreedGauge from '../components/dashboard/FearGreedGauge'
import toast from 'react-hot-toast'

const INTERVALS = [
  { label: '15m', value: '15' },
  { label: '1H',  value: '60' },
  { label: '4H',  value: '240' },
  { label: '1D',  value: 'D' },
  { label: '1W',  value: 'W' },
]

export default function Dashboard() {
  const { mode, selectedSymbol, setSelectedSymbol, selectedMarket, setSelectedMarket, engineRunning, setEngineRunning } = useStore()
  const [interval, setInterval] = useState('240')
  const [engLoading, setEngLoading] = useState(false)

  const cat = selectedMarket === 'spot' ? 'spot' : 'linear'

  const { data: klines } = useQuery({
    queryKey: ['klines', selectedSymbol, interval, cat],
    queryFn: () => marketApi.klines(selectedSymbol, interval, cat, 300).then(r => r.data.candles ?? []),
    refetchInterval: 60_000,
    placeholderData: [],
  })

  const { data: posData, refetch: refetchPositions } = useQuery({
    queryKey: ['positions', mode],
    queryFn: () => tradingApi.openPositions(mode).then(r => r.data),
    refetchInterval: 15_000,
  })

  const { data: pnl } = useQuery({
    queryKey: ['pnl', mode],
    queryFn: () => tradingApi.pnlSummary(mode).then(r => r.data),
    refetchInterval: 15_000,
  })

  const { data: fearGreed } = useQuery({
    queryKey: ['fear-greed'],
    queryFn: () => marketApi.fearGreed().then(r => r.data),
    refetchInterval: 300_000,
    placeholderData: { value: 50, zone: 'neutral' },
  })

  const isRunning = engineRunning[mode]

  async function toggleEngine() {
    setEngLoading(true)
    try {
      if (isRunning) {
        await tradingApi.stopEngine(mode)
        setEngineRunning(mode, false)
        toast('Engine stopped', { icon: '⏹' })
      } else {
        await tradingApi.startEngine(mode)
        setEngineRunning(mode, true)
        toast.success('Engine started')
      }
    } catch {}
    setEngLoading(false)
  }

  const candles = klines ?? []
  const positions = posData?.positions ?? []

  // Build price-line markers for open position in this symbol
  const markers = positions
    .filter((p: any) => p.symbol === selectedSymbol)
    .flatMap((p: any) => [
      { type: 'entry' as const, price: p.entry_price, time: 0, side: p.side.toLowerCase() },
      p.stop_loss && { type: 'sl' as const, price: p.stop_loss, time: 0 },
      !p.tp1_filled && p.tp1 && { type: 'tp1' as const, price: p.tp1, time: 0 },
      !p.tp2_filled && p.tp2 && { type: 'tp2' as const, price: p.tp2, time: 0 },
      !p.tp3_filled && p.tp3 && { type: 'tp3' as const, price: p.tp3, time: 0 },
    ])
    .filter(Boolean) as any[]

  function pnlClass(v: number) { return v >= 0 ? 'pnl-positive' : 'pnl-negative' }
  function fmt(v: number | undefined) { return v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}` : '—' }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold">Dashboard</h1>
        <span className="text-xs border border-voltage-border px-2 py-0.5 rounded font-mono uppercase text-voltage-accent">
          {mode}
        </span>
        <div className="flex-1" />
        <button
          onClick={toggleEngine}
          disabled={engLoading}
          className={isRunning ? 'btn-danger' : 'btn-primary'}
        >
          {engLoading
            ? <RefreshCw size={13} className="inline mr-1 animate-spin" />
            : isRunning
              ? <Square size={13} className="inline mr-1" />
              : <Play size={13} className="inline mr-1" />}
          {isRunning ? 'Stop Engine' : 'Start Engine'}
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: 'Unrealized PnL', value: fmt(pnl?.unrealized), raw: pnl?.unrealized ?? 0 },
          { label: "Today's PnL",    value: fmt(pnl?.today),       raw: pnl?.today ?? 0 },
          { label: 'Month PnL',      value: fmt(pnl?.month),       raw: pnl?.month ?? 0 },
          { label: 'Open Positions', value: String(pnl?.open_positions ?? 0), raw: 0 },
        ].map(({ label, value, raw }) => (
          <div key={label} className="stat-card">
            <span className="stat-label">{label}</span>
            <span className={`stat-value ${label !== 'Open Positions' ? pnlClass(raw) : 'text-voltage-text'}`}>
              {value}
            </span>
            {label !== 'Open Positions' && <span className="text-xs text-voltage-muted">USDT</span>}
          </div>
        ))}
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Chart */}
        <div className="xl:col-span-3 panel p-3">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <input
              className="w-32 text-sm"
              value={selectedSymbol}
              onChange={e => setSelectedSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol..."
            />
            <select
              value={selectedMarket}
              onChange={e => setSelectedMarket(e.target.value as 'spot' | 'futures')}
              className="text-sm"
            >
              <option value="spot">Spot</option>
              <option value="futures">Futures</option>
            </select>
            <div className="flex gap-1 ml-1">
              {INTERVALS.map(iv => (
                <button
                  key={iv.value}
                  onClick={() => setInterval(iv.value)}
                  className={`px-2 py-1 text-xs rounded transition-all ${
                    interval === iv.value
                      ? 'bg-voltage-accent/20 text-voltage-accent border border-voltage-accent/40'
                      : 'text-voltage-muted border border-transparent hover:text-voltage-text'
                  }`}
                >
                  {iv.label}
                </button>
              ))}
            </div>
          </div>
          <TradingChart
            candles={candles}
            markers={markers}
            height={380}
            symbol={selectedSymbol}
            interval={INTERVALS.find(i => i.value === interval)?.label}
          />
        </div>

        {/* Right column */}
        <div className="xl:col-span-1 flex flex-col gap-3">
          <FearGreedGauge
            value={fearGreed?.value ?? 50}
            zone={fearGreed?.zone ?? 'neutral'}
          />
          <BalancePanel mode={mode} />
          <AISignalPanel symbol={selectedSymbol} market={selectedMarket} mode={mode} />
        </div>
      </div>

      {/* Positions table */}
      <div className="panel p-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-voltage-border">
          <h2 className="text-sm font-semibold">Open Positions</h2>
          <button onClick={() => refetchPositions()} className="text-voltage-muted hover:text-voltage-text p-1">
            <RefreshCw size={13} />
          </button>
        </div>
        <PositionsTable positions={positions} mode={mode} onClose={() => refetchPositions()} />
      </div>
    </div>
  )
}
