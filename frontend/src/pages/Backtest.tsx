import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { backtestApi, marketApi } from '../api'
import { Play, Square, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

function formatProfitFactor(value: number | null | undefined, totalPnl?: number, losingTrades?: number) {
  if (value == null && (totalPnl ?? 0) > 0 && (losingTrades ?? 0) === 0) return '∞'
  return value?.toFixed(2) ?? '—'
}

export default function Backtest() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null)
  const [expandedResult, setExpandedResult] = useState(false)
  const [expandedDecisionLog, setExpandedDecisionLog] = useState(false)
  const [expandedAiLog, setExpandedAiLog] = useState(false)
  const [form, setForm] = useState({
    name: 'VOLTAGE Backtest',
    market_type: 'spot',
    start_date: '2023-01-01',
    end_date: '2024-01-01',
    initial_balance: 10000,
    risk_per_trade_pct: 2,
    ai_confidence_threshold: 0.60,
    leverage: 1,
  })
  const [selectedPairs, setSelectedPairs] = useState<string[]>(['BTCUSDT', 'ETHUSDT'])
  const [pairSearch, setPairSearch] = useState('')

  const { data: pairs } = useQuery({
    queryKey: ['backtest-pairs', form.market_type],
    queryFn: () => (form.market_type === 'spot' ? marketApi.spotPairs() : marketApi.futuresPairs()).then(r => r.data.pairs),
    enabled: showForm,
  })

  const { data: sessions } = useQuery({
    queryKey: ['backtest-sessions'],
    queryFn: () => backtestApi.sessions().then(r => r.data.sessions),
    refetchInterval: 5_000,
  })

  const { data: selectedSession } = useQuery({
    queryKey: ['backtest-session', selectedSessionId],
    queryFn: () => backtestApi.session(selectedSessionId as number).then(r => r.data),
    enabled: selectedSessionId != null,
    refetchInterval: selectedSessionId != null ? 5_000 : false,
  })

  const startMut = useMutation({
    mutationFn: (d: any) => backtestApi.start(d),
    onSuccess: (r) => {
      toast.success(`Backtest started: ${r.data.session_id}`)
      setShowForm(false)
      setSelectedSessionId(r.data.session_id)
      qc.invalidateQueries({ queryKey: ['backtest-sessions'] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => backtestApi.delete(id),
    onSuccess: () => { toast('Session deleted'); qc.invalidateQueries({ queryKey: ['backtest-sessions'] }) },
  })

  const clearMut = useMutation({
    mutationFn: () => backtestApi.clearAll(),
    onSuccess: () => {
      toast('All cleared')
      qc.invalidateQueries({ queryKey: ['backtest-sessions'] })
      setSelectedSessionId(null)
    },
  })

  const stopMut = useMutation({
    mutationFn: (id: number) => backtestApi.stop(id),
    onSuccess: () => {
      toast('Backtest stop requested')
      qc.invalidateQueries({ queryKey: ['backtest-sessions'] })
      if (selectedSessionId != null) {
        qc.invalidateQueries({ queryKey: ['backtest-session', selectedSessionId] })
      }
    },
  })

  function togglePair(p: string) {
    setSelectedPairs(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])
  }

  function submitBacktest() {
    if (selectedPairs.length === 0) { toast.error('Select at least one pair'); return }
    startMut.mutate({ ...form, symbols: selectedPairs, market_type: form.market_type })
  }

  const filteredPairs = (pairs || []).filter((p: string) => p.toLowerCase().includes(pairSearch.toLowerCase())).slice(0, 100)
  const tooltipStyle = { backgroundColor: '#111318', border: '1px solid #1e2230', color: '#e6edf3', fontSize: 11 }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold">Backtest</h1>
        <div className="flex-1" />
        {selectedSession?.status === 'running' && (
          <button
            onClick={() => stopMut.mutate(selectedSession.id)}
            disabled={stopMut.isPending}
            className="btn-danger text-xs"
          >
            <Square size={12} className="inline mr-1" /> Stop Selected
          </button>
        )}
        <button onClick={() => clearMut.mutate()} className="btn-ghost text-xs">Clear All</button>
        <button onClick={() => setShowForm(v => !v)} className="btn-primary">
          <Play size={12} className="inline mr-1" /> New Backtest
        </button>
      </div>

      {/* New backtest form */}
      {showForm && (
        <div className="panel p-5 space-y-4">
          <h2 className="text-sm font-semibold text-voltage-accent">Configure Backtest</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div><label>Name</label><input value={form.name} onChange={e => setForm({...form, name: e.target.value})} /></div>
            <div>
              <label>Market</label>
              <select value={form.market_type} onChange={e => setForm({...form, market_type: e.target.value, leverage: e.target.value === 'spot' ? 1 : form.leverage})} className="w-full">
                <option value="spot">Spot</option>
                <option value="futures">Futures (Linear)</option>
              </select>
            </div>
            <div><label>Start Date</label><input type="date" value={form.start_date} onChange={e => setForm({...form, start_date: e.target.value})} /></div>
            <div><label>End Date</label><input type="date" value={form.end_date} onChange={e => setForm({...form, end_date: e.target.value})} /></div>
            <div><label>Initial Balance (USDT)</label><input type="number" value={form.initial_balance} onChange={e => setForm({...form, initial_balance: +e.target.value})} /></div>
            <div><label>Risk per Trade (%)</label><input type="number" step="0.5" min="0.5" max="5" value={form.risk_per_trade_pct} onChange={e => setForm({...form, risk_per_trade_pct: +e.target.value})} /></div>
            <div><label>AI Confidence Threshold</label><input type="number" step="0.05" min="0.4" max="0.95" value={form.ai_confidence_threshold} onChange={e => setForm({...form, ai_confidence_threshold: +e.target.value})} /></div>
            {form.market_type === 'futures' && (
              <div><label>Leverage</label><input type="number" min="1" max="20" value={form.leverage} onChange={e => setForm({...form, leverage: +e.target.value})} /></div>
            )}
          </div>

          {/* Pair selector */}
          <div>
            <label className="flex justify-between">
              <span>Trading Pairs ({selectedPairs.length} selected)</span>
              <input value={pairSearch} onChange={e => setPairSearch(e.target.value)} placeholder="Search..." className="w-40 text-xs" />
            </label>
            <div className="border border-voltage-border rounded-md p-2 max-h-40 overflow-y-auto mt-1 flex flex-wrap gap-1">
              {filteredPairs.map((p: string) => (
                <button
                  key={p}
                  onClick={() => togglePair(p)}
                  className={clsx('px-2 py-0.5 text-xs rounded border transition-all',
                    selectedPairs.includes(p)
                      ? 'bg-voltage-accent/20 text-voltage-accent border-voltage-accent/50'
                      : 'text-voltage-muted border-voltage-border hover:border-voltage-accent/30'
                  )}
                >{p}</button>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
            <button onClick={submitBacktest} disabled={startMut.isPending} className="btn-primary">
              {startMut.isPending ? 'Starting...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Sessions list */}
        <div className="panel">
          <div className="px-4 py-3 border-b border-voltage-border text-sm font-semibold">Sessions</div>
          <div className="overflow-y-auto max-h-[600px]">
            {(sessions || []).length === 0 && (
              <div className="p-8 text-center text-voltage-muted text-sm">No backtest sessions yet</div>
            )}
            {(sessions || []).map((s: any) => (
              <button
                key={s.id}
                onClick={() => setSelectedSessionId(s.id)}
                className={clsx(
                  'w-full px-4 py-3 border-b border-voltage-border/50 text-left hover:bg-voltage-hover/30 transition-all',
                  selectedSessionId === s.id && 'bg-voltage-hover border-l-2 border-l-voltage-accent'
                )}
              >
                <div className="flex justify-between items-start">
                  <div className="text-sm font-semibold text-voltage-text truncate">{s.name}</div>
                  <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
                    <span className={clsx('text-[10px] px-1.5 py-0.5 rounded border',
                      s.status === 'done' ? 'text-voltage-green border-voltage-green/30' :
                      s.status === 'running' ? 'text-voltage-accent border-voltage-accent/30' :
                      s.status === 'stopping' ? 'text-voltage-accent border-voltage-accent/30' :
                      s.status === 'stopped' ? 'text-voltage-blue border-voltage-blue/30' :
                      s.status === 'error' ? 'text-voltage-red border-voltage-red/30' :
                      'text-voltage-muted border-voltage-border'
                    )}>{s.status}</span>
                    {s.status === 'running' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); stopMut.mutate(s.id) }}
                        className="text-voltage-muted hover:text-voltage-accent"
                        title="Stop backtest"
                      ><Square size={11} /></button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteMut.mutate(s.id) }}
                      className="text-voltage-muted hover:text-voltage-red"
                    ><Trash2 size={11} /></button>
                  </div>
                </div>
                <div className="text-xs text-voltage-muted mt-1">
                  {s.start_date?.slice(0,10)} → {s.end_date?.slice(0,10)} · {s.market_type}
                </div>
                {(s.status === 'running' || s.status === 'stopping') && (
                  <div className="mt-1.5 h-1 bg-voltage-border rounded overflow-hidden">
                    <div className="h-full bg-voltage-accent transition-all" style={{ width: `${(s.progress * 100).toFixed(0)}%` }} />
                  </div>
                )}
                {s.status === 'done' && (
                  <div className="flex gap-3 mt-1.5 text-xs font-mono">
                    <span className={s.total_pnl >= 0 ? 'text-voltage-green' : 'text-voltage-red'}>
                      {s.total_pnl >= 0 ? '+' : ''}{s.total_pnl?.toFixed(2)} USDT
                    </span>
                    <span className="text-voltage-muted">{s.win_rate?.toFixed(1)}% WR</span>
                    <span className="text-voltage-muted">{s.total_trades}T</span>
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Session detail */}
        <div className="xl:col-span-2 space-y-4">
          {selectedSession ? (
            <>
              {/* KPIs */}
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
                {[
                  ['Total Trades', selectedSession.total_trades],
                  ['Win Rate', `${selectedSession.win_rate?.toFixed(1)}%`],
                  ['Profit Factor', formatProfitFactor(selectedSession.profit_factor, selectedSession.total_pnl, selectedSession.losing_trades)],
                  ['Max Drawdown', `${selectedSession.max_drawdown?.toFixed(1)}%`],
                  ['ROI', `${((selectedSession.final_balance - selectedSession.initial_balance) / selectedSession.initial_balance * 100).toFixed(1)}%`],
                  ['Net PnL', `${selectedSession.total_pnl >= 0 ? '+' : ''}${selectedSession.total_pnl?.toFixed(2)}`],
                ].map(([label, value]) => (
                  <div key={label as string} className="stat-card">
                    <span className="stat-label">{label}</span>
                    <span className="stat-value text-base">{value}</span>
                  </div>
                ))}
              </div>

              {selectedSession.artifacts && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="stat-card">
                    <span className="stat-label">Persisted Trades</span>
                    <span className="stat-value text-base">{selectedSession.artifacts.persisted_trades}</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Journal Entries</span>
                    <span className="stat-value text-base">{selectedSession.artifacts.persisted_journal_entries}</span>
                  </div>
                </div>
              )}

              {selectedSession.results_data?.macro_context?.btc_dominance_source && (
                <div className="panel px-4 py-3 text-xs text-voltage-muted">
                  Macro context source:
                  <span className="ml-2 font-mono text-voltage-accent">
                    {selectedSession.results_data.macro_context.btc_dominance_source}
                  </span>
                </div>
              )}

              {selectedSession.results_data?.decision_stats && (
                <div className="panel p-4">
                  <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Decision Flow Summary</h3>
                  <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                    {Object.entries(selectedSession.results_data.decision_stats).map(([reason, count]) => (
                      <div key={reason} className="stat-card">
                        <span className="stat-label">{reason}</span>
                        <span className="stat-value text-base">{count as number}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(selectedSession.status === 'running' || selectedSession.status === 'stopping' || selectedSession.status === 'stopped') && (
                <div className="panel p-4">
                  <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Execution Progress</h3>
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <div className="stat-card">
                      <span className="stat-label">Status</span>
                      <span className="stat-value text-base uppercase">{selectedSession.status}</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-label">Progress</span>
                      <span className="stat-value text-base">{((selectedSession.progress ?? 0) * 100).toFixed(1)}%</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-label">Current Symbol</span>
                      <span className="stat-value text-base">{selectedSession.results_data?.progress_marker?.symbol ?? '—'}</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-label">Current Time</span>
                      <span className="stat-value text-base">{selectedSession.results_data?.progress_marker?.time?.slice?.(0,16) ?? '—'}</span>
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="h-2 bg-voltage-border rounded overflow-hidden">
                      <div className="h-full bg-voltage-accent transition-all" style={{ width: `${((selectedSession.progress ?? 0) * 100).toFixed(0)}%` }} />
                    </div>
                  </div>
                </div>
              )}

              {/* Equity Curve */}
              {selectedSession.results_data?.equity_curve?.length > 0 && (
                <div className="panel p-4">
                  <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Equity Curve</h3>
                  {selectedSession.results_data?.progress_marker && (
                    <div className="mb-3 flex items-center justify-between text-xs font-mono">
                      <span className="text-voltage-muted">
                        Current: <span className="text-voltage-accent">{selectedSession.results_data.progress_marker.symbol ?? '—'}</span>
                        {selectedSession.results_data.progress_marker.time ? ` @ ${selectedSession.results_data.progress_marker.time.slice(0,16)}` : ''}
                      </span>
                      <span className="text-voltage-muted">
                        Equity snapshot: <span className="text-voltage-text">{selectedSession.results_data.progress_marker.equity?.toFixed?.(2) ?? '—'} USDT</span>
                      </span>
                    </div>
                  )}
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={selectedSession.results_data.equity_curve}>
                      <defs>
                        <linearGradient id="btGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#00d395" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#00d395" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#8b949e' }} tickFormatter={v => v?.slice?.(0,10) || ''} />
                      <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => [`${v?.toFixed?.(2)} USDT`, 'Equity']} />
                      <Area type="monotone" dataKey="equity" stroke="#00d395" fill="url(#btGrad)" strokeWidth={2} dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Trades summary */}
              {selectedSession.results_data?.trades_summary?.length > 0 && (
                <div className="panel overflow-hidden">
                  <button
                    className="w-full flex items-center gap-2 px-4 py-3 border-b border-voltage-border text-sm font-semibold text-left"
                    onClick={() => setExpandedResult(v => !v)}
                  >
                    {expandedResult ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Trade-by-Trade Results ({selectedSession.results_data.trades_summary.length})
                  </button>
                  {expandedResult && (
                    <div className="overflow-x-auto max-h-96">
                      <table className="w-full text-xs font-mono">
                        <thead>
                          <tr className="text-voltage-muted border-b border-voltage-border">
                            {['Symbol','Side','Entry','Avg Exit','Final Exit','PnL','Conf.','Scenario','F&G','BTC.D','Exit Path','Reason'].map(h => (
                              <th key={h} className="px-3 py-2 text-left whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {selectedSession.results_data.trades_summary.map((t: any, i: number) => (
                            <tr key={i} className="border-b border-voltage-border/30 hover:bg-voltage-hover/10">
                              <td className="px-3 py-1.5 text-voltage-text">{t.symbol}</td>
                              <td className="px-3 py-1.5">
                                <span className={t.side === 'long' ? 'badge-long' : 'badge-short'}>{t.side}</span>
                              </td>
                              <td className="px-3 py-1.5">{t.entry?.toFixed(4)}</td>
                              <td className="px-3 py-1.5">{t.avg_exit != null ? t.avg_exit.toFixed(4) : '—'}</td>
                              <td className="px-3 py-1.5">{t.final_exit != null ? t.final_exit.toFixed(4) : '—'}</td>
                              <td className={`px-3 py-1.5 font-bold ${t.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                                {t.pnl >= 0 ? '+' : ''}{t.pnl?.toFixed(4)}
                              </td>
                              <td className="px-3 py-1.5 text-voltage-muted">
                                {t.confidence != null ? `${(t.confidence * 100).toFixed(0)}%` : '—'}
                              </td>
                              <td className="px-3 py-1.5 text-voltage-muted">{t.scenario ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{t.fear_greed ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">
                                {t.btc_dominance != null ? t.btc_dominance.toFixed(2) : '—'}
                              </td>
                              <td className="px-3 py-1.5 text-voltage-muted">{t.exit_path ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{t.reason_label ?? t.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {selectedSession.results_data?.decision_log?.length > 0 && (
                <div className="panel overflow-hidden">
                  <button
                    className="w-full flex items-center gap-2 px-4 py-3 border-b border-voltage-border text-sm font-semibold text-left"
                    onClick={() => setExpandedDecisionLog(v => !v)}
                  >
                    {expandedDecisionLog ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Decision Trail Samples ({selectedSession.results_data.decision_log.length})
                  </button>
                  {expandedDecisionLog && (
                    <div className="overflow-x-auto max-h-96">
                      <table className="w-full text-xs font-mono">
                        <thead>
                          <tr className="text-voltage-muted border-b border-voltage-border">
                            {['Time','Symbol','Reason','Signal','Conf.','Filters','Scenario','F&G','BTC.D'].map(h => (
                              <th key={h} className="px-3 py-2 text-left whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {selectedSession.results_data.decision_log.map((d: any, i: number) => (
                            <tr key={i} className="border-b border-voltage-border/30 hover:bg-voltage-hover/10">
                              <td className="px-3 py-1.5 text-voltage-muted">{d.time?.slice(0,16)}</td>
                              <td className="px-3 py-1.5 text-voltage-text">{d.symbol}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{d.reason}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{d.signal ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">
                                {d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : '—'}
                              </td>
                              <td className="px-3 py-1.5 text-voltage-muted">{d.filters_passed ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{d.scenario ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{d.fear_greed ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">
                                {d.btc_dominance != null ? d.btc_dominance.toFixed(2) : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {selectedSession.results_data?.ai_analyses?.length > 0 && (
                <div className="panel overflow-hidden">
                  <button
                    className="w-full flex items-center gap-2 px-4 py-3 border-b border-voltage-border text-sm font-semibold text-left"
                    onClick={() => setExpandedAiLog(v => !v)}
                  >
                    {expandedAiLog ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    AI Analyses ({selectedSession.results_data.ai_analyses.length})
                  </button>
                  {expandedAiLog && (
                    <div className="overflow-x-auto max-h-96">
                      <table className="w-full text-xs font-mono">
                        <thead>
                          <tr className="text-voltage-muted border-b border-voltage-border">
                            {['Time','Symbol','Signal','Conf.','Scenario','Decision','Reasoning'].map(h => (
                              <th key={h} className="px-3 py-2 text-left whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {selectedSession.results_data.ai_analyses.map((a: any, i: number) => (
                            <tr key={i} className="border-b border-voltage-border/30 hover:bg-voltage-hover/10 align-top">
                              <td className="px-3 py-1.5 text-voltage-muted">{a.time?.slice?.(0,16) ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-text">{a.symbol}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{a.signal ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{a.confidence != null ? `${(a.confidence * 100).toFixed(0)}%` : '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{a.scenario ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted">{a.decision_reason ?? '—'}</td>
                              <td className="px-3 py-1.5 text-voltage-muted min-w-[360px]">{a.reasoning || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="panel p-12 text-center text-voltage-muted">
              <p className="text-sm">Select a session to view results</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
