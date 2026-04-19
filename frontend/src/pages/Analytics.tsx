import { useQuery } from '@tanstack/react-query'
import { analyticsApi, journalApi } from '../api'
import { useStore } from '../store'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from 'recharts'

const COLORS = { profit: '#00d395', loss: '#f6465d', neutral: '#f0b90b', blue: '#3b82f6' }

function StatCard({ label, value, sub, color }: any) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={color ? { color } : undefined}>{value}</span>
      {sub && <span className="text-xs text-voltage-muted">{sub}</span>}
    </div>
  )
}

export default function Analytics() {
  const { mode } = useStore()

  const { data: ov } = useQuery({
    queryKey: ['analytics-overview', mode],
    queryFn: () => analyticsApi.overview(mode).then(r => r.data),
    refetchInterval: 60_000,
  })

  const { data: equity } = useQuery({
    queryKey: ['equity-curve', mode],
    queryFn: () => analyticsApi.equityCurve(mode).then(r => r.data),
  })

  const { data: heatmap } = useQuery({
    queryKey: ['heatmap', mode],
    queryFn: () => analyticsApi.heatmap(mode).then(r => r.data),
  })

  const { data: vfData } = useQuery({
    queryKey: ['voltage-filters', mode],
    queryFn: () => analyticsApi.voltageFilters(mode).then(r => r.data),
  })

  const { data: monthly } = useQuery({
    queryKey: ['journal-monthly', mode],
    queryFn: () => journalApi.monthlyPnl(mode).then(r => r.data),
  })

  if (!ov) return <div className="text-voltage-muted p-8 text-center">No analytics data yet. Start trading!</div>

  const pieData = [
    { name: 'Wins', value: ov.winning_trades },
    { name: 'Losses', value: ov.losing_trades },
  ]

  const sideData = [
    { name: 'Long', pnl: ov.longs?.pnl ?? 0, wr: ov.longs?.win_rate ?? 0, trades: ov.longs?.trades ?? 0 },
    { name: 'Short', pnl: ov.shorts?.pnl ?? 0, wr: ov.shorts?.win_rate ?? 0, trades: ov.shorts?.trades ?? 0 },
  ]

  const marketData = [
    { name: 'Spot', pnl: ov.spot?.pnl ?? 0, wr: ov.spot?.win_rate ?? 0, trades: ov.spot?.trades ?? 0 },
    { name: 'Futures', pnl: ov.futures?.pnl ?? 0, wr: ov.futures?.win_rate ?? 0, trades: ov.futures?.trades ?? 0 },
  ]

  const symbolData = Object.entries(ov.by_symbol || {})
    .map(([sym, s]: any) => ({ symbol: sym, pnl: s.pnl, win_rate: s.win_rate, trades: s.total }))
    .sort((a, b) => b.pnl - a.pnl)
    .slice(0, 15)

  const tooltipStyle = { backgroundColor: '#111318', border: '1px solid #1e2230', color: '#e6edf3', fontSize: 11 }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold">Analytics</h1>
        <span className="text-xs border border-voltage-border px-2 py-0.5 rounded font-mono uppercase">{mode}</span>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Total Trades" value={ov.total_trades} />
        <StatCard label="Win Rate" value={`${ov.win_rate?.toFixed(1)}%`} color={ov.win_rate >= 58 ? COLORS.profit : COLORS.loss} sub="Target ≥58%" />
        <StatCard label="Profit Factor" value={ov.profit_factor === Infinity ? '∞' : ov.profit_factor?.toFixed(2)} color={ov.profit_factor >= 2.2 ? COLORS.profit : COLORS.loss} sub="Target ≥2.2" />
        <StatCard label="Max Drawdown" value={`${ov.max_drawdown_pct?.toFixed(1)}%`} color={ov.max_drawdown_pct <= 18 ? COLORS.profit : COLORS.loss} sub="Limit 18%" />
        <StatCard label="Total PnL" value={`${ov.total_pnl >= 0 ? '+' : ''}${ov.total_pnl?.toFixed(2)}`} color={ov.total_pnl >= 0 ? COLORS.profit : COLORS.loss} sub="USDT" />
        <StatCard label="Avg Hold" value={`${ov.avg_hold_hours?.toFixed(1)}h`} sub="per trade" />
      </div>

      {/* Second row KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Best Trade" value={`+${ov.best_trade?.toFixed(2)} USDT`} color={COLORS.profit} />
        <StatCard label="Worst Trade" value={`${ov.worst_trade?.toFixed(2)} USDT`} color={COLORS.loss} />
        <StatCard label="Max Win Streak" value={ov.max_consecutive_wins} sub="consecutive" />
        <StatCard label="Max Loss Streak" value={ov.max_consecutive_losses} sub="consecutive" />
      </div>

      {/* Equity Curve + Win/Loss Pie */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Equity Curve</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={equity?.curve || []}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00d395" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d395" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#8b949e' }} tickFormatter={v => v?.slice?.(0,10) || ''} />
              <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => [`${v?.toFixed?.(2)} USDT`, 'Equity']} />
              <Area type="monotone" dataKey="equity" stroke="#00d395" fill="url(#equityGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel p-4 flex flex-col">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Win / Loss</h3>
          <div className="flex-1 flex items-center justify-center">
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={75} paddingAngle={3} dataKey="value">
                  <Cell fill={COLORS.profit} />
                  <Cell fill={COLORS.loss} />
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs">
            <div><div className="font-mono text-voltage-green font-bold">{ov.winning_trades}</div><div className="text-voltage-muted">Wins</div></div>
            <div><div className="font-mono text-voltage-red font-bold">{ov.losing_trades}</div><div className="text-voltage-muted">Losses</div></div>
            <div><div className="font-mono text-voltage-green">{ov.avg_win?.toFixed(2)}</div><div className="text-voltage-muted">Avg Win</div></div>
            <div><div className="font-mono text-voltage-red">{ov.avg_loss?.toFixed(2)}</div><div className="text-voltage-muted">Avg Loss</div></div>
          </div>
        </div>
      </div>

      {/* Monthly PnL + Direction breakdown */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Monthly PnL</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={monthly?.monthly || []}>
              <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#8b949e' }} />
              <YAxis tick={{ fontSize: 10, fill: '#8b949e' }} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => [`${v?.toFixed?.(2)} USDT`, 'PnL']} />
              <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                {(monthly?.monthly || []).map((m: any, i: number) => (
                  <Cell key={i} fill={m.pnl >= 0 ? COLORS.profit : COLORS.loss} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Long vs Short vs Market</h3>
          <div className="space-y-3">
            {[...sideData, ...marketData].map((d) => (
              <div key={d.name} className="flex items-center gap-3 text-sm">
                <span className="w-16 text-voltage-muted text-xs">{d.name}</span>
                <div className="flex-1 h-1.5 bg-voltage-border rounded overflow-hidden">
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${d.wr}%`,
                      background: d.wr >= 55 ? COLORS.profit : d.wr >= 45 ? COLORS.neutral : COLORS.loss,
                    }}
                  />
                </div>
                <span className="w-12 text-right font-mono text-xs text-voltage-muted">{d.wr.toFixed(1)}%WR</span>
                <span className={`w-20 text-right font-mono text-xs ${d.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                  {d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(2)}
                </span>
                <span className="w-8 text-right text-xs text-voltage-muted">{d.trades}T</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* VOLTAGE Filter Performance */}
      {vfData?.data?.length > 0 && (
        <div className="panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">VOLTAGE Filter Performance</h3>
          <p className="text-xs text-voltage-muted mb-3">Win rate and PnL grouped by how many filters passed at entry</p>
          <div className="grid grid-cols-7 gap-2">
            {vfData.data.map((d: any) => (
              <div key={d.filters_passed} className="panel p-3 text-center">
                <div className="text-xl font-mono font-bold text-voltage-accent">{d.filters_passed}/6</div>
                <div className={`text-sm font-mono mt-1 ${d.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                  {d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(1)}
                </div>
                <div className="text-xs text-voltage-muted">{d.win_rate}% WR</div>
                <div className="text-xs text-voltage-muted">{d.trades}T</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Symbol Performance */}
      {symbolData.length > 0 && (
        <div className="panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Performance by Symbol</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-voltage-muted border-b border-voltage-border">
                  {['Symbol','Trades','Win Rate','Total PnL'].map(h => (
                    <th key={h} className="px-3 py-2 text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbolData.map((s: any) => (
                  <tr key={s.symbol} className="border-b border-voltage-border/30 hover:bg-voltage-hover/20">
                    <td className="px-3 py-2 font-semibold text-voltage-text">{s.symbol}</td>
                    <td className="px-3 py-2">{s.trades}</td>
                    <td className="px-3 py-2">
                      <span className={s.win_rate >= 55 ? 'pnl-positive' : s.win_rate >= 45 ? 'text-voltage-accent' : 'pnl-negative'}>
                        {s.win_rate}%
                      </span>
                    </td>
                    <td className={`px-3 py-2 ${s.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                      {s.pnl >= 0 ? '+' : ''}{s.pnl.toFixed(2)} USDT
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PnL Heatmap */}
      {heatmap?.heatmap?.length > 0 && (
        <div className="panel p-4">
          <h3 className="text-sm font-semibold mb-3 text-voltage-muted uppercase tracking-wider">Daily PnL Heatmap</h3>
          <div className="flex flex-wrap gap-1">
            {(heatmap.heatmap as any[]).slice(-90).map((d: any) => {
              const intensity = Math.min(Math.abs(d.pnl) / 100, 1)
              const color = d.pnl > 0
                ? `rgba(0,211,149,${0.15 + intensity * 0.85})`
                : d.pnl < 0
                  ? `rgba(246,70,93,${0.15 + intensity * 0.85})`
                  : '#1e2230'
              return (
                <div
                  key={d.date}
                  title={`${d.date}: ${d.pnl >= 0 ? '+' : ''}${d.pnl.toFixed(2)} USDT`}
                  className="w-4 h-4 rounded-sm cursor-default"
                  style={{ backgroundColor: color }}
                />
              )
            })}
          </div>
          <div className="flex items-center gap-2 mt-2 text-[10px] text-voltage-muted">
            <div className="w-3 h-3 rounded-sm bg-voltage-red/60" /> Loss
            <div className="w-3 h-3 rounded-sm bg-voltage-border" /> Break-even
            <div className="w-3 h-3 rounded-sm bg-voltage-green/60" /> Profit
          </div>
        </div>
      )}
    </div>
  )
}
