import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, BookOpen, BarChart3, ClipboardList,
  Activity, FlaskConical, Settings, Wifi, WifiOff, Zap,
} from 'lucide-react'
import { useStore } from '../../store'
import { useWebSocket } from '../../hooks/useWebSocket'
import ModeSwitch from './ModeSwitch'
import clsx from 'clsx'

const NAV = [
  { to: '/',          label: 'Dashboard',  icon: LayoutDashboard },
  { to: '/trades',    label: 'Trades',     icon: Activity },
  { to: '/orders',    label: 'Orders',     icon: ClipboardList },
  { to: '/journal',   label: 'Journal',    icon: BookOpen },
  { to: '/analytics', label: 'Analytics',  icon: BarChart3 },
  { to: '/backtest',  label: 'Backtest',   icon: FlaskConical },
  { to: '/settings',  label: 'Settings',   icon: Settings },
]

export default function Layout() {
  const { wsConnected, livePnl, mode } = useStore()
  useWebSocket()   // Connect WS globally

  return (
    <div className="flex h-screen overflow-hidden bg-voltage-bg">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-voltage-border flex flex-col">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-voltage-border">
          <div className="flex items-center gap-2">
            <Zap size={20} className="text-voltage-accent" fill="currentColor" />
            <span className="text-lg font-bold tracking-widest text-voltage-accent font-mono">VOLTAGE</span>
          </div>
          <p className="text-[10px] text-voltage-muted mt-0.5 tracking-wider">AI TRADING SYSTEM</p>
        </div>

        {/* Mode switch */}
        <div className="px-4 py-3 border-b border-voltage-border">
          <ModeSwitch />
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-4 py-2.5 text-sm transition-all mx-2 rounded-md mb-0.5',
                  isActive
                    ? 'bg-voltage-accent/10 text-voltage-accent border border-voltage-accent/20'
                    : 'text-voltage-muted hover:text-voltage-text hover:bg-voltage-hover'
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer status */}
        <div className="px-4 py-3 border-t border-voltage-border space-y-1.5">
          <div className="flex items-center gap-2 text-xs">
            {wsConnected
              ? <><div className="w-1.5 h-1.5 rounded-full bg-voltage-green live-dot" /><span className="text-voltage-green">Live</span></>
              : <><WifiOff size={10} className="text-voltage-red" /><span className="text-voltage-red">Offline</span></>
            }
          </div>
          <div className="text-[10px] text-voltage-muted font-mono">
            Mode: <span className="text-voltage-accent uppercase">{mode}</span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <header className="h-12 flex-shrink-0 border-b border-voltage-border flex items-center px-4 gap-6">
          <div className="flex-1" />
          {/* Live PnL pills */}
          <div className="flex items-center gap-4 text-xs font-mono">
            <span className="text-voltage-muted">Unrealized:</span>
            <span className={livePnl.unrealized >= 0 ? 'text-voltage-green' : 'text-voltage-red'}>
              {livePnl.unrealized >= 0 ? '+' : ''}{livePnl.unrealized.toFixed(2)} USDT
            </span>
            <span className="text-voltage-muted">Today:</span>
            <span className={livePnl.today >= 0 ? 'text-voltage-green' : 'text-voltage-red'}>
              {livePnl.today >= 0 ? '+' : ''}{livePnl.today.toFixed(2)} USDT
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
