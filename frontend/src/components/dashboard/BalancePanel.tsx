import { useQuery } from '@tanstack/react-query'
import { tradingApi } from '../../api'

export default function BalancePanel({ mode }: { mode: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['balance', mode],
    queryFn: () => tradingApi.balance(mode).then(r => r.data),
    refetchInterval: 30_000,
  })

  if (isLoading || !data) {
    return <div className="panel p-3 h-24 animate-pulse bg-voltage-hover/40" />
  }

  const rows: [string, string][] =
    mode === 'real'
      ? [
          ['Available', `${(data.available_usdt ?? 0).toFixed(2)} USDT`],
          ['Total Equity', `${(data.total_usdt ?? 0).toFixed(2)} USDT`],
          ...(data.spot_allocated ? [['Spot Budget', `${data.spot_allocated.toFixed(2)}`] as [string, string]] : []),
          ...(data.futures_allocated ? [['Fut. Budget', `${data.futures_allocated.toFixed(2)}`] as [string, string]] : []),
        ]
      : mode === 'paper'
      ? [
          ['Spot Available', `${(data.spot_balance ?? data.spot_initial ?? 0).toFixed(2)} USDT`],
          ['Spot Equity', `${(data.spot_equity ?? data.spot_initial ?? 0).toFixed(2)} USDT`],
          ['Futures Available', `${(data.futures_balance ?? data.futures_initial ?? 0).toFixed(2)} USDT`],
          ['Futures Equity', `${(data.futures_equity ?? data.futures_initial ?? 0).toFixed(2)} USDT`],
          ['Total Available', `${(data.total_available ?? 0).toFixed(2)} USDT`],
          ['Total Equity', `${(data.total_equity ?? 0).toFixed(2)} USDT`],
        ]
      : [
          ['Spot', `${(data.spot_balance ?? data.spot_initial ?? 0).toFixed(2)} USDT`],
          ['Futures', `${(data.futures_balance ?? data.futures_initial ?? 0).toFixed(2)} USDT`],
          ['Total', `${((data.spot_balance ?? data.spot_initial ?? 0) + (data.futures_balance ?? data.futures_initial ?? 0)).toFixed(2)} USDT`],
        ]

  return (
    <div className="panel p-3 space-y-1.5">
      <p className="stat-label">Balance</p>
      {rows.map(([label, value], i) => (
        <div key={i} className="flex justify-between text-sm">
          <span className="text-voltage-muted">{label}</span>
          <span className={`font-mono ${i === rows.length - 1 ? 'text-voltage-accent' : 'text-voltage-text'}`}>
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}
