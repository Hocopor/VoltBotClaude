import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ordersApi } from '../api'
import { useStore } from '../store'
import { format } from 'date-fns'
import clsx from 'clsx'

const STATUS_COLORS: Record<string, string> = {
  Open: 'text-voltage-blue border-voltage-blue/40 bg-voltage-blue/10',
  Filled: 'text-voltage-green border-voltage-green/40 bg-voltage-green/10',
  Cancelled: 'text-voltage-muted border-voltage-border',
  Rejected: 'text-voltage-red border-voltage-red/40 bg-voltage-red/10',
  PartiallyFilled: 'text-voltage-accent border-voltage-accent/40 bg-voltage-accent/10',
  Triggered: 'text-purple-400 border-purple-400/40 bg-purple-400/10',
  Pending: 'text-voltage-muted border-voltage-border',
  Expired: 'text-voltage-muted border-voltage-border',
}

export function Orders() {
  const { mode } = useStore()
  const [statusFilter, setStatusFilter] = useState('all')
  const [marketFilter, setMarketFilter] = useState('all')

  const { data, isLoading } = useQuery({
    queryKey: ['orders', mode, statusFilter, marketFilter],
    queryFn: () => ordersApi.list({
      mode,
      ...(statusFilter !== 'all' && { status: statusFilter }),
      ...(marketFilter !== 'all' && { market_type: marketFilter }),
      limit: 200,
    }).then(r => r.data),
    refetchInterval: 15_000,
  })

  const orders = data?.orders || []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-bold">Orders</h1>
        <span className="text-xs border border-voltage-border px-2 py-0.5 rounded font-mono uppercase">{mode}</span>
        <div className="flex-1" />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="text-xs">
          <option value="all">All Status</option>
          <option value="Open">Open</option>
          <option value="Filled">Filled</option>
          <option value="Cancelled">Cancelled</option>
          <option value="StopLoss">Stop Loss</option>
          <option value="TakeProfit">Take Profit</option>
          <option value="Triggered">Triggered</option>
        </select>
        <select value={marketFilter} onChange={e => setMarketFilter(e.target.value)} className="text-xs">
          <option value="all">All Markets</option>
          <option value="spot">Spot</option>
          <option value="futures">Futures</option>
        </select>
      </div>

      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-voltage-muted border-b border-voltage-border">
                {['ID','Symbol','Market','Type','Side','Status','Price','Stop Price','Qty','Filled','Avg Fill','Fee','Time'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr><td colSpan={13} className="px-4 py-8 text-center text-voltage-muted">Loading...</td></tr>
              )}
              {!isLoading && orders.length === 0 && (
                <tr><td colSpan={13} className="px-4 py-8 text-center text-voltage-muted">No orders found</td></tr>
              )}
              {orders.map((o: any) => (
                <tr key={o.id} className="border-b border-voltage-border/40 hover:bg-voltage-hover/20">
                  <td className="px-3 py-2 text-voltage-muted">{o.id}</td>
                  <td className="px-3 py-2 text-voltage-text font-semibold">{o.symbol}</td>
                  <td className="px-3 py-2">
                    <span className={o.market_type === 'spot' ? 'badge-spot' : 'badge-futures'}>{o.market_type}</span>
                  </td>
                  <td className="px-3 py-2 text-voltage-muted">{o.order_type}</td>
                  <td className="px-3 py-2">
                    <span className={o.side === 'Buy' ? 'badge-long' : 'badge-short'}>{o.side}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={clsx('px-1.5 py-0.5 rounded text-[10px] border', STATUS_COLORS[o.status] || 'text-voltage-muted')}>
                      {o.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">{o.price?.toFixed(4) ?? '—'}</td>
                  <td className="px-3 py-2 text-voltage-red">{o.stop_price?.toFixed(4) ?? '—'}</td>
                  <td className="px-3 py-2">{o.qty?.toFixed(4)}</td>
                  <td className="px-3 py-2 text-voltage-muted">{o.filled_qty?.toFixed(4)}</td>
                  <td className="px-3 py-2">{o.avg_fill_price?.toFixed(4) ?? '—'}</td>
                  <td className="px-3 py-2 text-voltage-muted">{o.fee?.toFixed(4)}</td>
                  <td className="px-3 py-2 text-voltage-muted">
                    {o.created_at ? format(new Date(o.created_at), 'dd/MM HH:mm:ss') : '—'}
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

export default Orders
