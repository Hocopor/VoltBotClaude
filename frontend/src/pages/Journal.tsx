import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { journalApi, marketApi } from '../api'
import { useStore } from '../store'
import TradingChart from '../components/charts/TradingChart'
import { format } from 'date-fns'
import { Brain, ChevronDown, ChevronRight, Star, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

export default function Journal() {
  const { mode } = useStore()
  const qc = useQueryClient()
  const [selected, setSelected] = useState<any>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [symbol, setSymbol] = useState('')
  const [dateFrom, setDateFrom] = useState('')

  const { data } = useQuery({
    queryKey: ['journal', mode, symbol, dateFrom],
    queryFn: () => journalApi.list({
      mode,
      ...(symbol && { symbol }),
      ...(dateFrom && { date_from: dateFrom }),
    }).then(r => r.data),
  })

  const { data: dayPnl } = useQuery({
    queryKey: ['journal-daily', mode],
    queryFn: () => journalApi.dailyPnl(mode).then(r => r.data),
  })

  const { data: monthPnl } = useQuery({
    queryKey: ['journal-monthly', mode],
    queryFn: () => journalApi.monthlyPnl(mode).then(r => r.data),
  })

  const analyzeMut = useMutation({
    mutationFn: (id: number) => journalApi.analyze(id),
    onSuccess: () => { toast.success('AI analysis complete'); qc.invalidateQueries({ queryKey: ['journal'] }) },
  })

  const clearMut = useMutation({
    mutationFn: () => journalApi.clear(mode),
    onSuccess: () => { toast('History cleared'); qc.invalidateQueries({ queryKey: ['journal'] }) },
  })

  // Fetch chart data for selected entry
  const { data: chartData } = useQuery({
    queryKey: ['chart-for-journal', selected?.symbol, selected?.entry_time],
    queryFn: async () => {
      if (!selected) return []
      const cat = selected.market_type === 'spot' ? 'spot' : 'linear'
      const r = await marketApi.klines(selected.symbol, '60', cat, 200)
      return r.data.candles
    },
    enabled: !!selected,
  })

  const entries = data?.entries || []

  function pnlClass(v: number) { return v > 0 ? 'pnl-positive' : v < 0 ? 'pnl-negative' : 'pnl-neutral' }

  const markers = selected ? [
    selected.entry_price && { type: 'entry', price: selected.entry_price, time: 0 },
    selected.exit_price  && { type: 'exit',  price: selected.exit_price,  time: 0 },
    selected.stop_loss   && { type: 'sl',    price: selected.stop_loss,   time: 0 },
    selected.take_profits?.tp1 && { type: 'tp1', price: selected.take_profits.tp1, time: 0 },
    selected.take_profits?.tp2 && { type: 'tp2', price: selected.take_profits.tp2, time: 0 },
    selected.take_profits?.tp3 && { type: 'tp3', price: selected.take_profits.tp3, time: 0 },
  ].filter(Boolean) : []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold">Journal</h1>
        <span className="text-xs border border-voltage-border px-2 py-0.5 rounded font-mono uppercase">{mode}</span>
        <div className="flex-1" />
        {mode !== 'real' && (
          <button
            onClick={() => clearMut.mutate()}
            className="btn-danger flex items-center gap-1"
          >
            <Trash2 size={12} /> Clear History
          </button>
        )}
      </div>

      {/* Monthly summary */}
      <div className="panel p-4">
        <h2 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Monthly PnL</h2>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {(monthPnl?.monthly || []).slice(-6).map((m: any) => (
            <div key={m.month} className="panel p-3 min-w-[130px] text-center">
              <div className="text-xs text-voltage-muted mb-1">{m.month}</div>
              <div className={`text-base font-mono font-bold ${pnlClass(m.pnl)}`}>
                {m.pnl >= 0 ? '+' : ''}{m.pnl.toFixed(2)}
              </div>
              <div className="text-xs text-voltage-muted">{m.win_rate}% WR · {m.trades}T</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        {/* Trade list */}
        <div className="xl:col-span-2 panel">
          <div className="flex gap-2 p-3 border-b border-voltage-border">
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="Symbol..." className="flex-1 text-xs" />
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="text-xs" />
          </div>
          <div className="overflow-y-auto max-h-[600px]">
            {entries.length === 0 && (
              <div className="p-8 text-center text-voltage-muted text-sm">No journal entries yet</div>
            )}
            {entries.map((e: any) => (
              <button
                key={e.id}
                onClick={() => setSelected(e)}
                className={clsx(
                  'w-full px-4 py-3 border-b border-voltage-border/50 text-left hover:bg-voltage-hover/40 transition-all',
                  selected?.id === e.id && 'bg-voltage-hover border-l-2 border-l-voltage-accent'
                )}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <span className="font-mono font-semibold text-sm text-voltage-text">{e.symbol}</span>
                    <span className={clsx('ml-2 text-xs', e.side === 'Long' ? 'badge-long' : 'badge-short')}>{e.side}</span>
                    <span className={clsx('ml-1 text-xs', e.market_type === 'spot' ? 'badge-spot' : 'badge-futures')}>{e.market_type}</span>
                  </div>
                  <span className={`font-mono text-sm ${pnlClass(e.net_pnl)}`}>
                    {e.net_pnl >= 0 ? '+' : ''}{e.net_pnl?.toFixed(2)} USDT
                  </span>
                </div>
                <div className="flex justify-between mt-1 text-xs text-voltage-muted">
                  <span>{e.entry_time ? format(new Date(e.entry_time), 'dd MMM HH:mm') : '—'}</span>
                  <span className="font-mono">{e.pnl_percent >= 0 ? '+' : ''}{e.pnl_percent?.toFixed(2)}%</span>
                </div>
                {e.ai_score != null && (
                  <div className="flex items-center gap-1 mt-1">
                    {[...Array(10)].map((_, i) => (
                      <Star key={i} size={8} className={i < Math.round(e.ai_score) ? 'text-voltage-accent fill-voltage-accent' : 'text-voltage-border'} />
                    ))}
                    <span className="text-[10px] text-voltage-muted ml-1">{e.ai_score?.toFixed(1)}/10</span>
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Detail panel */}
        <div className="xl:col-span-3 space-y-4">
          {selected ? (
            <>
              {/* Chart */}
              <div className="panel p-3">
                <TradingChart candles={chartData || []} markers={markers as any} height={280} symbol={selected.symbol} interval="1H" />
              </div>

              {/* Trade info */}
              <div className="panel p-4">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  {[
                    ['Symbol', selected.symbol],
                    ['Side', selected.side],
                    ['Market', selected.market_type],
                    ['Entry Price', selected.entry_price?.toFixed(6)],
                    ['Exit Price', selected.exit_price?.toFixed(6) ?? '—'],
                    ['Stop Loss', selected.stop_loss?.toFixed(6) ?? '—'],
                    ['TP1', selected.take_profits?.tp1?.toFixed(6) ?? '—'],
                    ['TP2', selected.take_profits?.tp2?.toFixed(6) ?? '—'],
                    ['TP3', selected.take_profits?.tp3?.toFixed(6) ?? '—'],
                    ['TP1 Hit', selected.take_profits?.tp1_hit ? '✅' : '❌'],
                    ['TP2 Hit', selected.take_profits?.tp2_hit ? '✅' : '❌'],
                    ['TP3 Hit', selected.take_profits?.tp3_hit ? '✅' : '❌'],
                    ['Realized PnL', `${selected.realized_pnl?.toFixed(4)} USDT`],
                    ['Fees', `${selected.fees?.toFixed(4)} USDT`],
                    ['Net PnL', `${selected.net_pnl >= 0 ? '+' : ''}${selected.net_pnl?.toFixed(4)} USDT`],
                    ['PnL %', `${selected.pnl_percent >= 0 ? '+' : ''}${selected.pnl_percent?.toFixed(2)}%`],
                    ['Entry', selected.entry_time ? format(new Date(selected.entry_time), 'dd MMM yyyy HH:mm') : '—'],
                    ['Exit', selected.exit_time ? format(new Date(selected.exit_time), 'dd MMM yyyy HH:mm') : '—'],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between border-b border-voltage-border/30 pb-1">
                      <span className="text-voltage-muted">{label}</span>
                      <span className={`font-mono text-right ${label.includes('PnL') ? (parseFloat(String(value)) >= 0 ? 'pnl-positive' : 'pnl-negative') : 'text-voltage-text'}`}>
                        {String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* AI Analysis */}
              <div className="panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Brain size={16} className="text-voltage-accent" />
                    <h3 className="text-sm font-semibold">AI Post-Trade Analysis</h3>
                  </div>
                  {!selected.ai_post_analysis && (
                    <button
                      onClick={() => analyzeMut.mutate(selected.id)}
                      disabled={analyzeMut.isPending}
                      className="btn-primary py-1 px-3 text-xs"
                    >
                      {analyzeMut.isPending ? 'Analyzing...' : 'Run AI Analysis'}
                    </button>
                  )}
                </div>
                {selected.ai_post_analysis ? (
                  <div className="space-y-3">
                    {selected.ai_score != null && (
                      <div className="flex items-center gap-3">
                        <span className="text-voltage-muted text-sm">Trade Quality:</span>
                        <div className="flex gap-1">
                          {[...Array(10)].map((_, i) => (
                            <Star key={i} size={14} className={i < Math.round(selected.ai_score) ? 'text-voltage-accent fill-voltage-accent' : 'text-voltage-border'} />
                          ))}
                        </div>
                        <span className="font-mono text-voltage-accent">{selected.ai_score?.toFixed(1)}/10</span>
                      </div>
                    )}
                    <div className="bg-voltage-hover/40 rounded-lg p-3 text-sm text-voltage-text leading-relaxed whitespace-pre-wrap">
                      {selected.ai_post_analysis}
                    </div>
                    {selected.ai_lessons && (
                      <div className="bg-voltage-accent/5 border border-voltage-accent/20 rounded-lg p-3">
                        <div className="text-xs text-voltage-accent font-semibold mb-1 uppercase tracking-wider">Lessons & Improvements</div>
                        <div className="text-sm text-voltage-text">{selected.ai_lessons}</div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-voltage-muted text-sm">
                    AI analysis is generated after trade closes. Click "Run AI Analysis" to request it.
                  </p>
                )}
              </div>

              {/* VOLTAGE Filter Snapshot */}
              {selected.voltage_snapshot && (
                <div className="panel p-4">
                  <button
                    className="flex items-center gap-2 text-sm font-semibold w-full text-left"
                    onClick={() => setExpanded(expanded === selected.id ? null : selected.id)}
                  >
                    {expanded === selected.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    VOLTAGE Filters at Entry
                  </button>
                  {expanded === selected.id && (
                    <div className="mt-3 space-y-2">
                      {[1,2,3,4,5,6].map(n => {
                        const f = (selected.voltage_snapshot as any)[`filter${n}`]
                        if (!f) return null
                        return (
                          <div key={n} className="flex items-start gap-3 text-xs">
                            <span className={clsx('mt-0.5 font-mono font-bold w-12 flex-shrink-0', f.passed ? 'text-voltage-green' : 'text-voltage-red')}>
                              F{n} {f.passed ? '✓' : '✗'}
                            </span>
                            <div>
                              <div className="text-voltage-muted">{(f.notes || []).join(' · ')}</div>
                              <div className="mt-0.5 h-1 w-24 bg-voltage-border rounded overflow-hidden">
                                <div className="h-full bg-voltage-accent" style={{ width: `${(f.score * 100).toFixed(0)}%` }} />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="panel p-12 text-center text-voltage-muted">
              <BookOpenIcon />
              <p className="mt-2 text-sm">Select a trade to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function BookOpenIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto mb-2 opacity-20" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
    </svg>
  )
}
