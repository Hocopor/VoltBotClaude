import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { settingsApi, authApi, marketApi } from '../api'
import { useStore } from '../store'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { CheckCircle, XCircle, ExternalLink, Save, Shield } from 'lucide-react'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel p-5 space-y-4">
      <h2 className="text-sm font-semibold text-voltage-accent uppercase tracking-wider border-b border-voltage-border pb-2">{title}</h2>
      {children}
    </div>
  )
}

export default function Settings() {
  const { mode } = useStore()
  const qc = useQueryClient()
  const { codexConnected, deepseekConfigured, bybitConfigured, setAuthStatus } = useStore()
  const [selectedSpotPairs, setSelectedSpotPairs] = useState<string[]>([])
  const [selectedFutPairs, setSelectedFutPairs] = useState<string[]>([])
  const [spotSearch, setSpotSearch] = useState('')
  const [futSearch, setFutSearch] = useState('')

  const { data: settings, refetch } = useQuery({
    queryKey: ['settings', mode],
    queryFn: () => settingsApi.get(mode).then(r => r.data),
  })

  const { data: spotPairs } = useQuery({
    queryKey: ['spot-pairs'],
    queryFn: () => marketApi.spotPairs().then(r => r.data.pairs),
  })

  const { data: futPairs } = useQuery({
    queryKey: ['fut-pairs'],
    queryFn: () => marketApi.futuresPairs().then(r => r.data.pairs),
  })

  useEffect(() => {
    if (settings) {
      setSelectedSpotPairs(settings.spot_pairs || [])
      setSelectedFutPairs(settings.futures_pairs || [])
    }
  }, [settings])

  const updateMut = useMutation({
    mutationFn: (d: any) => settingsApi.update(mode, d),
    onSuccess: () => { toast.success('Settings saved'); refetch() },
  })

  function Field({ label, name, type = 'number', step, min, max, value, onChange }: any) {
    return (
      <div>
        <label>{label}</label>
        <input type={type} step={step} min={min} max={max} value={value} onChange={onChange} className="w-full" />
      </div>
    )
  }

  function togglePair(set: React.Dispatch<React.SetStateAction<string[]>>, p: string) {
    set(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])
  }

  function PairSelector({ pairs, selected, onToggle, search, setSearch, label }: any) {
    const filtered = (pairs || []).filter((p: string) => p.toLowerCase().includes(search.toLowerCase())).slice(0, 150)
    return (
      <div>
        <div className="flex items-center justify-between mb-1">
          <label>{label} ({selected.length} selected)</label>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter..." className="w-32 text-xs" />
        </div>
        <div className="border border-voltage-border rounded-md p-2 h-48 overflow-y-auto flex flex-wrap gap-1 content-start">
          {filtered.map((p: string) => (
            <button
              key={p}
              onClick={() => onToggle(p)}
              className={clsx('px-2 py-0.5 text-xs rounded border transition-all',
                selected.includes(p)
                  ? 'bg-voltage-accent/20 text-voltage-accent border-voltage-accent/50'
                  : 'text-voltage-muted border-voltage-border hover:border-voltage-accent/30'
              )}
            >{p}</button>
          ))}
        </div>
      </div>
    )
  }

  function savePairs() {
    updateMut.mutate({
      spot_pairs: selectedSpotPairs,
      futures_pairs: selectedFutPairs,
    })
  }

  async function startCodexOAuth() {
    try {
      const r = await authApi.codexLoginUrl()
      window.open(r.data.auth_url, '_blank', 'width=500,height=700')
    } catch {}
  }

  if (!settings) return <div className="text-voltage-muted p-8 text-center">Loading...</div>

  return (
    <div className="space-y-4 max-w-4xl">
      <h1 className="text-lg font-bold">Settings</h1>
      <div className="text-xs border border-voltage-border rounded px-3 py-1.5 text-voltage-muted inline-flex items-center gap-2">
        Configuring mode: <span className="font-mono font-bold text-voltage-accent uppercase">{mode}</span>
        <span className="text-voltage-border">|</span> Each mode has independent settings
      </div>

      {/* Auth */}
      <Section title="Authentication & API Keys">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Bybit */}
          <div className="panel p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Bybit API</span>
              {bybitConfigured
                ? <CheckCircle size={14} className="text-voltage-green" />
                : <XCircle size={14} className="text-voltage-red" />
              }
            </div>
            <div className="flex items-start gap-2 text-xs text-voltage-muted bg-voltage-hover rounded p-2">
              <Shield size={14} className="mt-0.5 text-voltage-accent" />
              <div>
                <p className="text-voltage-text font-semibold">Managed via server `.env`</p>
                <p>Set `BYBIT_API_KEY` and `BYBIT_API_SECRET` on the server. The web UI does not store production secrets.</p>
              </div>
            </div>
          </div>

          {/* DeepSeek */}
          <div className="panel p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">DeepSeek AI</span>
              {deepseekConfigured
                ? <CheckCircle size={14} className="text-voltage-green" />
                : <XCircle size={14} className="text-voltage-red" />
              }
            </div>
            <div className="flex items-start gap-2 text-xs text-voltage-muted bg-voltage-hover rounded p-2">
              <Shield size={14} className="mt-0.5 text-voltage-accent" />
              <div>
                <p className="text-voltage-text font-semibold">Managed via server `.env`</p>
                <p>Set `DEEPSEEK_API_KEY` on the server. The web UI will later control model behavior, not raw secret storage.</p>
              </div>
            </div>
          </div>

          {/* Codex OAuth */}
          <div className="panel p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Codex (OpenAI)</span>
              {codexConnected
                ? <CheckCircle size={14} className="text-voltage-green" />
                : <XCircle size={14} className="text-voltage-muted" />
              }
            </div>
            {codexConnected ? (
              <>
                <div className="text-xs text-voltage-green">✅ Connected via OAuth</div>
                <button onClick={() => authApi.codexDisconnect().then(() => setAuthStatus({ codex: false, deepseek: deepseekConfigured, bybit: bybitConfigured }))} className="btn-danger w-full text-xs">Disconnect</button>
              </>
            ) : (
              <>
                <p className="text-xs text-voltage-muted">Login with your OpenAI/Codex account for enhanced AI analysis.</p>
                <button onClick={startCodexOAuth} className="btn-primary w-full text-xs flex items-center justify-center gap-1">
                  <ExternalLink size={12} /> Login with Codex
                </button>
              </>
            )}
          </div>
        </div>
      </Section>

      {/* Trading Pairs */}
      <Section title="Trading Pairs">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PairSelector
            pairs={spotPairs}
            selected={selectedSpotPairs}
            onToggle={(p: string) => togglePair(setSelectedSpotPairs, p)}
            search={spotSearch}
            setSearch={setSpotSearch}
            label="Spot Pairs (USDT)"
          />
          <PairSelector
            pairs={futPairs}
            selected={selectedFutPairs}
            onToggle={(p: string) => togglePair(setSelectedFutPairs, p)}
            search={futSearch}
            setSearch={setFutSearch}
            label="Futures Pairs (Linear)"
          />
        </div>
        <button onClick={savePairs} disabled={updateMut.isPending} className="btn-primary flex items-center gap-1">
          <Save size={13} /> Save Pairs
        </button>
      </Section>

      {/* Market enable/disable */}
      <Section title="Market Settings">
        <div className="grid grid-cols-2 gap-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={settings.spot_enabled} onChange={e => updateMut.mutate({ spot_enabled: e.target.checked })} className="w-4 h-4 accent-yellow-400" />
            <span className="text-sm">Enable Spot Trading</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={settings.futures_enabled} onChange={e => updateMut.mutate({ futures_enabled: e.target.checked })} className="w-4 h-4 accent-yellow-400" />
            <span className="text-sm">Enable Futures Trading</span>
          </label>
        </div>
      </Section>

      {/* Balance */}
      <Section title="Balance Configuration">
        {mode === 'real' && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label>Spot Trading Budget (USDT)</label>
              <input type="number" defaultValue={settings.spot_allocated_balance || ''} onBlur={e => updateMut.mutate({ spot_allocated_balance: +e.target.value || null })} placeholder="Leave empty = use full balance" />
            </div>
            <div>
              <label>Futures Trading Budget (USDT)</label>
              <input type="number" defaultValue={settings.futures_allocated_balance || ''} onBlur={e => updateMut.mutate({ futures_allocated_balance: +e.target.value || null })} placeholder="Leave empty = use full balance" />
            </div>
          </div>
        )}
        {mode === 'paper' && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label>Paper Spot Initial Balance (USDT)</label>
              <input type="number" defaultValue={settings.paper_initial_balance_spot} onBlur={e => updateMut.mutate({ paper_initial_balance_spot: +e.target.value })} />
            </div>
            <div>
              <label>Paper Futures Initial Balance (USDT)</label>
              <input type="number" defaultValue={settings.paper_initial_balance_futures} onBlur={e => updateMut.mutate({ paper_initial_balance_futures: +e.target.value })} />
            </div>
            <div className="col-span-2 text-xs text-voltage-muted bg-voltage-hover rounded p-2">
              Current balances: Spot {settings.paper_current_balance_spot?.toFixed(2)} USDT · Futures {settings.paper_current_balance_futures?.toFixed(2)} USDT
            </div>
          </div>
        )}
        {mode === 'backtest' && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label>Backtest Spot Starting Balance (USDT)</label>
              <input type="number" defaultValue={settings.backtest_initial_balance_spot} onBlur={e => updateMut.mutate({ backtest_initial_balance_spot: +e.target.value })} />
            </div>
            <div>
              <label>Backtest Futures Starting Balance (USDT)</label>
              <input type="number" defaultValue={settings.backtest_initial_balance_futures} onBlur={e => updateMut.mutate({ backtest_initial_balance_futures: +e.target.value })} />
            </div>
          </div>
        )}
      </Section>

      {/* Strategy params */}
      <Section title="VOLTAGE Strategy Parameters">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label>Risk per Trade (%)</label>
            <input type="number" step="0.5" min="0.5" max="5" defaultValue={settings.risk_per_trade_pct} onBlur={e => updateMut.mutate({ risk_per_trade_pct: +e.target.value })} />
            <p className="text-[10px] text-voltage-muted mt-1">VOLTAGE: 1-3% recommended</p>
          </div>
          <div>
            <label>Max Open Positions</label>
            <input type="number" min="1" max="20" defaultValue={settings.max_open_positions} onBlur={e => updateMut.mutate({ max_open_positions: +e.target.value })} />
          </div>
          <div>
            <label>AI Confidence Threshold</label>
            <input type="number" step="0.05" min="0.5" max="0.95" defaultValue={settings.ai_confidence_threshold} onBlur={e => updateMut.mutate({ ai_confidence_threshold: +e.target.value })} />
            <p className="text-[10px] text-voltage-muted mt-1">Minimum confidence to enter (0-1)</p>
          </div>
          <div>
            <label>Scan Frequency (minutes)</label>
            <input type="number" min="1" max="1440" defaultValue={settings.scan_interval_minutes ?? (mode === 'backtest' ? 240 : 15)} onBlur={e => updateMut.mutate({ scan_interval_minutes: +e.target.value })} />
            <p className="text-[10px] text-voltage-muted mt-1">
              {mode === 'backtest'
                ? 'Captured when a new backtest session starts.'
                : 'Running engine picks up updated value on the next cycle.'}
            </p>
          </div>
          <div>
            <label>Default Leverage (Futures)</label>
            <input type="number" min="1" max="20" defaultValue={settings.default_leverage} onBlur={e => updateMut.mutate({ default_leverage: +e.target.value })} />
          </div>
        </div>

        <div className="panel p-4 mt-2 text-xs text-voltage-muted space-y-1">
          <p className="font-semibold text-voltage-text">VOLTAGE Risk Management Rules (Fixed):</p>
          <p>• TP1 = 1.5R → close 40% of position, move SL to breakeven</p>
          <p>• TP2 = 3.0R → close 30% of position</p>
          <p>• TP3 = 5.0R → close remaining 30% + activate trailing stop</p>
          <p>• SL for altcoins: 8-12% from entry | SL for BTC/ETH: 5-8% from entry</p>
          <p>• Max 3 positions per sector (DeFi, AI, Meme, etc.)</p>
        </div>
      </Section>

      {/* Auto trading toggle */}
      <Section title="Automation">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.auto_trading_enabled}
            onChange={e => updateMut.mutate({ auto_trading_enabled: e.target.checked })}
            className="w-4 h-4 accent-yellow-400"
          />
          <div>
            <span className="text-sm font-semibold">Auto Trading Enabled</span>
            <p className="text-xs text-voltage-muted">When enabled, the bot automatically places orders when AI confidence clears the threshold and the minimum VOLTAGE filter gate passes.</p>
          </div>
        </label>
      </Section>
    </div>
  )
}
