import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { tradesApi } from '../api'
import { useStore } from '../store'
import { format } from 'date-fns'
import clsx from 'clsx'

export default function Trades() {
  const { mode } = useStore()
  const [statusFilter, setStatusFilter] = useState('all')
  const [marketFilter, setMarketFilter] = useState('all')
  const [sideFilter, setSideFilter] = useState('all')

  const { data, isLoading } = useQuery({
    queryKey: ['trades', mode, statusFilter, marketFilter, sideFilter],
    queryFn: () => tradesApi.list({
      mode,
      ...(statusFilter !== 'all' && { status: statusFilter }),
      ...(marketFilter !== 'all' && { market_type: marketFilter }),
      ...(sideFilter !== 'all' && { side: sideFilter }),
      limit: 200,
    }).then(r => r.data),
    refetchInterval: 15_000,
  })

  const trades = data?.trades || []

  function pnlClass(v: number) { return v > 0 ? 'pnl-positive' : v < 0 ? 'pnl-negative' : 'pnl-neutral' }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold">Trades</h1>
        <span className="text-xs border border-voltage-border px-2 py-0.5 rounded font-mono uppercase">{mode}</span>
        <div className="flex-1" />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-xs">
          <option value="all">All Status</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select value={marketFilter} onChange={e => setMarketFilter(e.target.value)} className="text-xs">
          <option value="all">All Markets</option>
          <option value="spot">Spot</option>
          <option value="futures">Futures</option>
        </select>
        <select value={sideFilter} onChange={e => setSideFilter(e.target.value)} className="text-xs">
          <option value="all">Long & Short</option>
          <option value="Long">Long</option>
          <option value="Short">Short</option>
        </select>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-4 gap-3">
        {['open','closed','cancelled'].map(s => {
          const count = trades.filter((t: any) => t.status === s).length
          const pnl = trades.filter((t: any) => t.status === s).reduce((a: number, t: any) => a + t.net_pnl, 0)
          return (
            <div key={s} className="stat-card">
              <span className="stat-label capitalize">{s}</span>
              <span className="stat-value">{count}</span>
              {s !== 'open' && <span className={`text-xs font-mono ${pnlClass(pnl)}`}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} USDT</span>}
            </div>
          )
        })}
        <div className="stat-card">
          <span className="stat-label">Total PnL</span>
          <span className={`stat-value ${pnlClass(trades.reduce((a: number, t: any) => a + t.net_pnl, 0))}`}>
            {trades.reduce((a: number, t: any) => a + t.net_pnl, 0) >= 0 ? '+' : ''}
            {trades.reduce((a: number, t: any) => a + t.net_pnl, 0).toFixed(2)}
          </span>
        </div>
      </div>

      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-voltage-muted border-b border-voltage-border">
                {['ID','Symbol','Market','Side','Status','Entry','Exit','SL','TP1','TP2','TP3','Qty','Realized PnL','Unrealized PnL','Net PnL','Fees','Leverage','AI Conf.','Entry Time','Exit Time'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={20} className="px-4 py-8 text-center text-voltage-muted">Loading...</td></tr>
              )}
              {!isLoading && trades.length === 0 && (
                <tr><td colSpan={20} className="px-4 py-8 text-center text-voltage-muted">No trades found</td></tr>
              )}
              {trades.map((t: any) => (
                <tr key={t.id} className="border-b border-voltage-border/40 hover:bg-voltage-hover/20">
                  <td className="px-3 py-2 text-voltage-muted">{t.id}</td>
                  <td className="px-3 py-2 text-voltage-text font-semibold">{t.symbol}</td>
                  <td className="px-3 py-2">
                    <span className={t.market_type === 'spot' ? 'badge-spot' : 'badge-futures'}>{t.market_type}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={t.side === 'Long' ? 'badge-long' : 'badge-short'}>{t.side}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={clsx('px-1.5 py-0.5 rounded text-[10px] border',
                      t.status === 'open' ? 'text-voltage-blue border-voltage-blue/40 bg-voltage-blue/10'
                      : t.status === 'closed' ? 'text-voltage-green border-voltage-green/40 bg-voltage-green/10'
                      : 'text-voltage-muted border-voltage-border'
                    )}>{t.status}</span>
                  </td>
                  <td className="px-3 py-2">{t.entry_price?.toFixed(4)}</td>
                  <td className="px-3 py-2">{t.exit_price?.toFixed(4) ?? '—'}</td>
                  <td className="px-3 py-2 text-voltage-red">{t.stop_loss?.toFixed(4) ?? '—'}</td>
                  <td className={clsx('px-3 py-2', t.tp1_filled ? 'line-through text-voltage-muted' : 'text-voltage-green/70')}>
                    {t.tp1?.toFixed(4) ?? '—'}</td>
                  <td className={clsx('px-3 py-2', t.tp2_filled ? 'line-through text-voltage-muted' : 'text-voltage-green/85')}>
                    {t.tp2?.toFixed(4) ?? '—'}</td>
                  <td className={clsx('px-3 py-2', t.tp3_filled ? 'line-through text-voltage-muted' : 'text-voltage-green')}>
                    {t.tp3?.toFixed(4) ?? '—'}</td>
                  <td className="px-3 py-2">{t.entry_qty?.toFixed(4)}</td>
                  <td className={`px-3 py-2 ${pnlClass(t.realized_pnl)}`}>{t.realized_pnl >= 0 ? '+' : ''}{t.realized_pnl?.toFixed(4)}</td>
                  <td className={`px-3 py-2 ${pnlClass(t.unrealized_pnl)}`}>{t.unrealized_pnl >= 0 ? '+' : ''}{t.unrealized_pnl?.toFixed(4)}</td>
                  <td className={`px-3 py-2 font-bold ${pnlClass(t.net_pnl)}`}>{t.net_pnl >= 0 ? '+' : ''}{t.net_pnl?.toFixed(4)}</td>
                  <td className="px-3 py-2 text-voltage-muted">{t.fees?.toFixed(4)}</td>
                  <td className="px-3 py-2 text-voltage-muted">{t.leverage}x</td>
                  <td className="px-3 py-2">
                    {t.ai_confidence != null ? (
                      <div className="flex items-center gap-1">
                        <div className="w-8 h-1.5 bg-voltage-border rounded overflow-hidden">
                          <div className="h-full bg-voltage-accent" style={{ width: `${(t.ai_confidence * 100).toFixed(0)}%` }} />
                        </div>
                        <span className="text-voltage-muted">{(t.ai_confidence * 100).toFixed(0)}%</span>
                      </div>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-2 text-voltage-muted whitespace-nowrap">
                    {t.entry_time ? format(new Date(t.entry_time), 'dd/MM HH:mm') : '—'}
                  </td>
                  <td className="px-3 py-2 text-voltage-muted whitespace-nowrap">
                    {t.exit_time ? format(new Date(t.exit_time), 'dd/MM HH:mm') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
