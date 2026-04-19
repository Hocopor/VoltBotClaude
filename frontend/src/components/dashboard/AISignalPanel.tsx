import { useQuery } from '@tanstack/react-query'
import { tradingApi } from '../../api'
import clsx from 'clsx'

const SIGNAL_COLOR: Record<string, string> = {
  long:    'text-voltage-green',
  short:   'text-voltage-red',
  neutral: 'text-voltage-muted',
  wait:    'text-voltage-accent',
}

const SIGNAL_BG: Record<string, string> = {
  long:    'bg-voltage-green/10 border-voltage-green/30',
  short:   'bg-voltage-red/10 border-voltage-red/30',
  neutral: 'bg-voltage-border/20 border-voltage-border',
  wait:    'bg-voltage-accent/10 border-voltage-accent/30',
}

export default function AISignalPanel({
  symbol, market, mode,
}: {
  symbol: string
  market: string
  mode: string
}) {
  const { data: posData } = useQuery({
    queryKey: ['positions', mode],
    queryFn: () => tradingApi.openPositions(mode).then(r => r.data),
    refetchInterval: 15_000,
  })

  const pos = (posData?.positions ?? []).find((p: any) => p.symbol === symbol)
  const signal = pos?.ai_signal?.toLowerCase() ?? null
  const conf = pos?.ai_confidence ?? null

  return (
    <div className="panel p-3 flex-1 flex flex-col gap-2">
      <p className="stat-label">AI Signal — {symbol}</p>

      {signal ? (
        <>
          <div className={clsx(
            'px-3 py-1.5 rounded border text-center',
            SIGNAL_BG[signal] ?? 'bg-voltage-border/20 border-voltage-border'
          )}>
            <span className={clsx('text-lg font-mono font-bold uppercase', SIGNAL_COLOR[signal] ?? 'text-voltage-muted')}>
              {signal}
            </span>
          </div>

          {conf != null && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-voltage-muted">Confidence</span>
                <span className="font-mono text-voltage-text">{(conf * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full h-1.5 bg-voltage-border rounded overflow-hidden">
                <div
                  className="h-full bg-voltage-accent transition-all duration-700"
                  style={{ width: `${(conf * 100).toFixed(0)}%` }}
                />
              </div>
            </div>
          )}

          {pos?.ai_analysis_entry && (
            <p className="text-[10px] text-voltage-muted leading-relaxed line-clamp-3">
              {pos.ai_analysis_entry}
            </p>
          )}
        </>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-2">
          <div className="text-2xl mb-1 opacity-30">⚡</div>
          <p className="text-xs text-voltage-muted">
            Engine scans {symbol} every 15 min using all 6 VOLTAGE filters.
          </p>
          <p className="text-[10px] text-voltage-border mt-1">
            Start the engine to see live signals.
          </p>
        </div>
      )}
    </div>
  )
}
