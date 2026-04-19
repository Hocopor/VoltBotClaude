export default function FearGreedGauge({ value, zone }: { value: number; zone: string }) {
  const color =
    value <= 25 ? '#f6465d' :
    value <= 45 ? '#f97316' :
    value <= 55 ? '#f0b90b' :
    value <= 75 ? '#84cc16' : '#00d395'

  const label =
    value <= 25 ? 'Extreme Fear' :
    value <= 45 ? 'Fear' :
    value <= 55 ? 'Neutral' :
    value <= 75 ? 'Greed' : 'Extreme Greed'

  const hint =
    value <= 25 ? '🟢 Accumulation zone — consider buying' :
    value > 25 && value <= 45 ? '✅ Good entry conditions' :
    value > 45 && value <= 55 ? '😐 Neutral market' :
    value > 55 && value <= 75 ? '⚠️ Elevated greed — caution' :
    '🔴 Distribution zone — avoid longs'

  return (
    <div className="panel p-3">
      <p className="stat-label mb-2">Fear & Greed Index</p>
      <div className="relative py-1">
        <div className="w-full h-2 rounded-full bg-gradient-to-r from-voltage-red via-voltage-accent to-voltage-green relative">
          <div
            className="absolute w-3 h-3 rounded-full border-2 border-voltage-panel shadow-lg transition-all duration-500"
            style={{
              left: `calc(${Math.min(Math.max(value, 2), 98)}% - 6px)`,
              top: '50%', transform: 'translateY(-50%)',
              backgroundColor: color,
            }}
          />
        </div>
      </div>
      <div className="flex justify-between items-end mt-2">
        <span className="text-2xl font-mono font-bold" style={{ color }}>{value}</span>
        <span className="text-xs font-semibold" style={{ color }}>{label}</span>
      </div>
      <p className="mt-1 text-[10px] text-voltage-muted">{hint}</p>
    </div>
  )
}
