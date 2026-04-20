import { useMutation, useQuery } from '@tanstack/react-query'
import { settingsApi, tradingApi } from '../../api'
import clsx from 'clsx'
import { useState } from 'react'
import toast from 'react-hot-toast'

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
  const [manualResult, setManualResult] = useState<any>(null)
  const { data: posData } = useQuery({
    queryKey: ['positions', mode],
    queryFn: () => tradingApi.openPositions(mode).then(r => r.data),
    refetchInterval: 15_000,
  })
  const { data: settings } = useQuery({
    queryKey: ['settings-ai-panel', mode],
    queryFn: () => settingsApi.get(mode).then(r => r.data),
    enabled: mode !== 'backtest',
  })

  const pos = (posData?.positions ?? []).find((p: any) => p.symbol === symbol)
  const signal = manualResult?.signal?.toLowerCase() ?? pos?.ai_signal?.toLowerCase() ?? null
  const conf = manualResult?.confidence ?? pos?.ai_confidence ?? null
  const reasoning = manualResult?.reasoning ?? pos?.ai_analysis_entry ?? null
  const scenario = manualResult?.scenario ?? null
  const filtersPassed = manualResult?.filters_passed ?? null

  const analyzeMut = useMutation({
    mutationFn: () => tradingApi.analyze({ mode, symbol, market_type: market === 'futures' ? 'futures' : 'spot' }),
    onSuccess: (r) => {
      setManualResult(r.data)
      toast.success(`AI analysis ready: ${r.data.signal?.toUpperCase?.() || 'DONE'}`)
    },
  })

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

          {reasoning && (
            <p className="text-[10px] text-voltage-muted leading-relaxed line-clamp-3">
              {reasoning}
            </p>
          )}

          {(scenario || filtersPassed != null) && (
            <div className="flex items-center justify-between text-[10px] text-voltage-muted font-mono gap-2">
              <span>{scenario ? `Scenario: ${scenario}` : 'Scenario: —'}</span>
              <span>{filtersPassed != null ? `Filters: ${filtersPassed}/6` : 'Filters: —'}</span>
            </div>
          )}
        </>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-2">
          <div className="text-2xl mb-1 opacity-30">⚡</div>
          <p className="text-xs text-voltage-muted">
            {mode === 'backtest'
              ? 'Backtest does not use the live engine button. Run historical sessions from the Backtest page.'
              : `Engine scans ${symbol} on the configured schedule (${settings?.scan_interval_minutes ?? 15} min) using the VOLTAGE pipeline.`}
          </p>
          <p className="text-[10px] text-voltage-border mt-1">
            {mode === 'backtest'
              ? 'Use the Backtest page for historical runs and results.'
              : 'Start the engine to see live signals.'}
          </p>
        </div>
      )}

      <button
        onClick={() => analyzeMut.mutate()}
        disabled={analyzeMut.isPending}
        className="btn-ghost text-xs mt-auto"
      >
        {analyzeMut.isPending ? 'Analyzing...' : 'Run AI Analysis'}
      </button>
    </div>
  )
}
