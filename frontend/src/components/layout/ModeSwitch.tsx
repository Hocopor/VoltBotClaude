import { useStore, TradingMode } from '../../store'
import clsx from 'clsx'

const MODES: { value: TradingMode; label: string; color: string }[] = [
  { value: 'real',     label: 'Real',    color: 'text-voltage-green border-voltage-green/40 bg-voltage-green/10' },
  { value: 'paper',    label: 'Paper',   color: 'text-voltage-accent border-voltage-accent/40 bg-voltage-accent/10' },
  { value: 'backtest', label: 'Backtest',color: 'text-voltage-blue border-voltage-blue/40 bg-voltage-blue/10' },
]

export default function ModeSwitch() {
  const { mode, setMode } = useStore()

  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] text-voltage-muted uppercase tracking-wider mb-1">Trading Mode</p>
      {MODES.map(({ value, label, color }) => (
        <button
          key={value}
          onClick={() => setMode(value)}
          className={clsx(
            'w-full py-1.5 px-2 rounded text-xs font-semibold border transition-all text-left',
            mode === value ? color : 'text-voltage-muted border-voltage-border hover:border-voltage-border/60'
          )}
        >
          <span className={clsx('inline-block w-1.5 h-1.5 rounded-full mr-2',
            mode === value ? 'bg-current' : 'bg-voltage-border'
          )} />
          {label}
        </button>
      ))}
    </div>
  )
}
