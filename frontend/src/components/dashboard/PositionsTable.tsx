// ─── PositionsTable ─────────────────────────────────────────
import { tradingApi } from '../../api'
import toast from 'react-hot-toast'

interface Position {
  id: number; symbol: string; market_type: string; side: string
  entry_price: number; current_price: number; qty: number; remaining_qty: number
  stop_loss: number; tp1: number; tp2: number; tp3: number
  tp1_filled: boolean; tp2_filled: boolean; tp3_filled: boolean
  realized_pnl: number; unrealized_pnl: number; net_pnl: number
  leverage: number; ai_confidence: number; entry_time: string
  trailing_stop_active: boolean
}

interface PTProps {
  positions: Position[]
  mode: string
  onClose: () => void
}

export function PositionsTable({ positions, mode, onClose }: PTProps) {
  async function closePos(id: number) {
    try {
      await tradingApi.closeTrade(id, mode)
      toast.success('Position closed')
      onClose()
    } catch {}
  }

  if (!positions.length) {
    return <div className="px-4 py-8 text-center text-voltage-muted text-sm">No open positions</div>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-voltage-muted border-b border-voltage-border">
            {['Symbol','Type','Side','Entry','Current','SL','TP1','TP2','TP3','Unr.PnL','Real.PnL','Conf.','Action'].map(h => (
              <th key={h} className="px-3 py-2 text-left whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.id} className="border-b border-voltage-border/50 hover:bg-voltage-hover/30">
              <td className="px-3 py-2 font-semibold text-voltage-text">{p.symbol}</td>
              <td className="px-3 py-2">
                <span className={p.market_type === 'spot' ? 'badge-spot' : 'badge-futures'}>{p.market_type}</span>
              </td>
              <td className="px-3 py-2">
                <span className={p.side === 'Long' ? 'badge-long' : 'badge-short'}>{p.side}</span>
              </td>
              <td className="px-3 py-2">{p.entry_price.toFixed(4)}</td>
              <td className="px-3 py-2">{p.current_price.toFixed(4)}</td>
              <td className="px-3 py-2 text-voltage-red">{p.stop_loss?.toFixed(4) ?? '—'}</td>
              <td className={`px-3 py-2 ${p.tp1_filled ? 'line-through text-voltage-muted' : 'text-voltage-green/70'}`}>
                {p.tp1?.toFixed(4) ?? '—'}
              </td>
              <td className={`px-3 py-2 ${p.tp2_filled ? 'line-through text-voltage-muted' : 'text-voltage-green/85'}`}>
                {p.tp2?.toFixed(4) ?? '—'}
              </td>
              <td className={`px-3 py-2 ${p.tp3_filled ? 'line-through text-voltage-muted' : 'text-voltage-green'}`}>
                {p.tp3?.toFixed(4) ?? '—'}
              </td>
              <td className={`px-3 py-2 ${p.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl.toFixed(2)}
              </td>
              <td className={`px-3 py-2 ${p.realized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                {p.realized_pnl >= 0 ? '+' : ''}{p.realized_pnl.toFixed(2)}
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1">
                  <div className="w-10 h-1.5 bg-voltage-border rounded overflow-hidden">
                    <div
                      className="h-full bg-voltage-accent rounded"
                      style={{ width: `${((p.ai_confidence || 0) * 100).toFixed(0)}%` }}
                    />
                  </div>
                  <span className="text-voltage-muted">{((p.ai_confidence || 0) * 100).toFixed(0)}%</span>
                </div>
              </td>
              <td className="px-3 py-2">
                <button onClick={() => closePos(p.id)} className="btn-danger py-1 px-2 text-xs">
                  Close
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default PositionsTable
