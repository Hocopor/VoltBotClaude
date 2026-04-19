import { useEffect, useRef } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle, IChartApi, ISeriesApi } from 'lightweight-charts'

interface Candle {
  timestamp: number
  open: number; high: number; low: number; close: number; volume: number
}

interface TradeMarker {
  type: 'entry' | 'exit' | 'sl' | 'tp1' | 'tp2' | 'tp3'
  price: number
  time: number
  side?: 'long' | 'short'
}

interface Props {
  candles: Candle[]
  markers?: TradeMarker[]
  height?: number
  symbol?: string
  interval?: string
}

export default function TradingChart({ candles, markers = [], height = 420, symbol, interval }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#111318' },
        textColor: '#8b949e',
      },
      grid: {
        vertLines: { color: '#1e2230' },
        horzLines: { color: '#1e2230' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1e2230' },
      timeScale: { borderColor: '#1e2230', timeVisible: true, secondsVisible: false },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#00d395',
      downColor: '#f6465d',
      borderUpColor: '#00d395',
      borderDownColor: '#f6465d',
      wickUpColor: '#00d395',
      wickDownColor: '#f6465d',
    })

    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      color: '#1e2230',
    })

    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })

    chartRef.current = chart
    candleRef.current = candleSeries
    volRef.current = volSeries

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [height])

  // Update data
  useEffect(() => {
    if (!candleRef.current || !volRef.current || !candles.length) return

    const cdata = candles.map((c) => ({
      time: Math.floor(c.timestamp / 1000) as any,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }))

    const vdata = candles.map((c) => ({
      time: Math.floor(c.timestamp / 1000) as any,
      value: c.volume,
      color: c.close >= c.open ? '#00d39520' : '#f6465d20',
    }))

    candleRef.current.setData(cdata)
    volRef.current.setData(vdata)

    // Price lines for trade markers
    if (chartRef.current) {
      const priceLinesColor: Record<string, string> = {
        entry: '#f0b90b',
        sl: '#f6465d',
        tp1: '#00d39580',
        tp2: '#00d395b0',
        tp3: '#00d395',
        exit: '#3b82f6',
      }
      const priceLineLabels: Record<string, string> = {
        entry: 'Entry', sl: 'SL', tp1: 'TP1', tp2: 'TP2', tp3: 'TP3', exit: 'Exit',
      }
      markers.forEach((m) => {
        candleRef.current?.createPriceLine({
          price: m.price,
          color: priceLinesColor[m.type] || '#8b949e',
          lineWidth: 1,
          lineStyle: m.type === 'sl' ? LineStyle.Dashed : LineStyle.Solid,
          axisLabelVisible: true,
          title: priceLineLabels[m.type] || m.type,
        })
      })
    }
  }, [candles, markers])

  return (
    <div className="relative">
      {symbol && (
        <div className="absolute top-2 left-3 z-10 flex items-center gap-2">
          <span className="text-sm font-mono font-bold text-voltage-text">{symbol}</span>
          {interval && <span className="text-xs text-voltage-muted">{interval}</span>}
        </div>
      )}
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden tv-chart" style={{ height }} />
    </div>
  )
}
