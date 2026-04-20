"""
VOLTAGE Bot — Complete Database Models
All entities for trading modes: REAL, PAPER, BACKTEST
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
import enum

from sqlalchemy import (
    String, Numeric, Integer, Boolean, DateTime, Text,
    ForeignKey, Enum as SAEnum, JSON, Float, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class TradingMode(str, enum.Enum):
    REAL = "real"
    PAPER = "paper"
    BACKTEST = "backtest"


class MarketType(str, enum.Enum):
    SPOT = "spot"
    FUTURES = "futures"


class OrderSide(str, enum.Enum):
    BUY = "Buy"
    SELL = "Sell"


class OrderType(str, enum.Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    STOP_LOSS = "StopLoss"
    TAKE_PROFIT = "TakeProfit"
    STOP_LIMIT = "StopLimit"
    TRAILING_STOP = "TrailingStop"


class OrderStatus(str, enum.Enum):
    PENDING = "Pending"
    OPEN = "Open"
    FILLED = "Filled"
    PARTIALLY_FILLED = "PartiallyFilled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    TRIGGERED = "Triggered"
    EXPIRED = "Expired"


class PositionSide(str, enum.Enum):
    LONG = "Long"
    SHORT = "Short"
    NONE = "None"


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class AISignal(str, enum.Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    WAIT = "wait"


def enum_column(enum_cls: type[enum.Enum], enum_name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=enum_name,
        values_callable=lambda members: [member.value for member in members],
    )


# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────

class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[TradingMode] = mapped_column(enum_column(TradingMode, "tradingmode"), unique=True)

    # Active pairs (JSON list)
    spot_pairs: Mapped[dict] = mapped_column(JSON, default=list)
    futures_pairs: Mapped[dict] = mapped_column(JSON, default=list)

    # Trading enabled
    spot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    futures_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Balance controls
    spot_allocated_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    futures_allocated_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Paper / Backtest starting balance
    paper_initial_balance_spot: Mapped[float] = mapped_column(Float, default=10000.0)
    paper_initial_balance_futures: Mapped[float] = mapped_column(Float, default=10000.0)
    paper_current_balance_spot: Mapped[float] = mapped_column(Float, default=10000.0)
    paper_current_balance_futures: Mapped[float] = mapped_column(Float, default=10000.0)

    # Backtest date range
    backtest_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    backtest_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    backtest_initial_balance_spot: Mapped[float] = mapped_column(Float, default=10000.0)
    backtest_initial_balance_futures: Mapped[float] = mapped_column(Float, default=10000.0)

    # Strategy params (VOLTAGE)
    risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=5)
    max_positions_per_sector: Mapped[int] = mapped_column(Integer, default=3)
    ai_confidence_threshold: Mapped[float] = mapped_column(Float, default=0.72)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)

    # Leverage (futures)
    default_leverage: Mapped[int] = mapped_column(Integer, default=3)

    # Misc
    auto_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# AUTH TOKENS (OAuth / API Keys storage)
# ─────────────────────────────────────────────

class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))   # "codex", "deepseek"
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[TradingMode] = mapped_column(enum_column(TradingMode, "tradingmode"), index=True)
    market_type: Mapped[MarketType] = mapped_column(enum_column(MarketType, "markettype"))

    # Exchange data
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)

    # Order details
    side: Mapped[OrderSide] = mapped_column(enum_column(OrderSide, "orderside"))
    order_type: Mapped[OrderType] = mapped_column(enum_column(OrderType, "ordertype"))
    status: Mapped[OrderStatus] = mapped_column(enum_column(OrderStatus, "orderstatus"), default=OrderStatus.PENDING)
    position_side: Mapped[PositionSide] = mapped_column(enum_column(PositionSide, "positionside"), default=PositionSide.NONE)

    # Prices & quantities
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    qty: Mapped[float] = mapped_column(Float)
    filled_qty: Mapped[float] = mapped_column(Float, default=0.0)
    avg_fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Stop / TP links
    trade_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("trades.id"), nullable=True)
    parent_order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)

    # Fees
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    fee_currency: Mapped[str] = mapped_column(String(10), default="USDT")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI context
    ai_signal: Mapped[Optional[AISignal]] = mapped_column(enum_column(AISignal, "aisignal"), nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Backtest session
    backtest_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("backtest_sessions.id"), nullable=True)

    # Relations
    trade: Mapped[Optional["Trade"]] = relationship("Trade", back_populates="orders", foreign_keys=[trade_id])
    children: Mapped[list["Order"]] = relationship("Order", foreign_keys=[parent_order_id])

    __table_args__ = (
        Index("ix_orders_mode_symbol", "mode", "symbol"),
        Index("ix_orders_mode_status", "mode", "status"),
    )


# ─────────────────────────────────────────────
# TRADES (positions lifecycle)
# ─────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[TradingMode] = mapped_column(enum_column(TradingMode, "tradingmode"), index=True)
    market_type: Mapped[MarketType] = mapped_column(enum_column(MarketType, "markettype"))

    symbol: Mapped[str] = mapped_column(String(30), index=True)
    side: Mapped[PositionSide] = mapped_column(enum_column(PositionSide, "positionside"))
    status: Mapped[TradeStatus] = mapped_column(enum_column(TradeStatus, "tradestatus"), default=TradeStatus.OPEN)

    # Entry
    entry_price: Mapped[float] = mapped_column(Float)
    entry_qty: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Exit
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_qty: Mapped[float] = mapped_column(Float, default=0.0)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Risk management
    stop_loss_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_1_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_2_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_3_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp1_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    tp2_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    tp3_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_stop_active: Mapped[bool] = mapped_column(Boolean, default=False)
    trailing_stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # P&L
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees_total: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)

    # Leverage (futures)
    leverage: Mapped[int] = mapped_column(Integer, default=1)

    # AI analysis
    ai_signal: Mapped[Optional[AISignal]] = mapped_column(enum_column(AISignal, "aisignal"), nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_analysis_entry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_analysis_exit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_filters_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # VOLTAGE filter snapshot at entry
    voltage_filters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Backtest
    backtest_session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("backtest_sessions.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relations
    orders: Mapped[list[Order]] = relationship("Order", back_populates="trade", foreign_keys=[Order.trade_id])
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry", back_populates="trade", uselist=False)

    __table_args__ = (
        Index("ix_trades_mode_symbol", "mode", "symbol"),
        Index("ix_trades_mode_status", "mode", "status"),
    )


# ─────────────────────────────────────────────
# JOURNAL
# ─────────────────────────────────────────────

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_id: Mapped[int] = mapped_column(Integer, ForeignKey("trades.id"), unique=True)
    mode: Mapped[TradingMode] = mapped_column(enum_column(TradingMode, "tradingmode"), index=True)

    # Trade reference data (denormalized for journal display)
    symbol: Mapped[str] = mapped_column(String(30))
    market_type: Mapped[MarketType] = mapped_column(enum_column(MarketType, "markettype"))
    side: Mapped[PositionSide] = mapped_column(enum_column(PositionSide, "positionside"))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profits: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # {tp1, tp2, tp3, tp1_hit, ...}
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # P&L
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_percent: Mapped[float] = mapped_column(Float, default=0.0)

    # AI analysis (post-trade)
    ai_post_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_lessons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # Trade quality 0-10

    # VOLTAGE filter state at entry
    voltage_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Chart snapshot (OHLCV data for journal chart)
    chart_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Manual notes by user
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # list of tags

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relations
    trade: Mapped[Trade] = relationship("Trade", back_populates="journal_entry")


# ─────────────────────────────────────────────
# BACKTEST SESSIONS
# ─────────────────────────────────────────────

class BacktestSession(Base):
    __tablename__ = "backtest_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    symbols: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # list of symbols
    market_type: Mapped[MarketType] = mapped_column(enum_column(MarketType, "markettype"))

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    initial_balance: Mapped[float] = mapped_column(Float)
    final_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Results summary
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_rr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, done, error
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Full results JSON
    results_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ─────────────────────────────────────────────
# MARKET DATA CACHE
# ─────────────────────────────────────────────

class MarketDataCache(Base):
    __tablename__ = "market_data_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    timeframe: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index("ix_market_data_symbol_tf_ts", "symbol", "timeframe", "timestamp", unique=True),
    )


# ─────────────────────────────────────────────
# AI ANALYSIS LOG
# ─────────────────────────────────────────────

class AIAnalysisLog(Base):
    __tablename__ = "ai_analysis_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[TradingMode] = mapped_column(enum_column(TradingMode, "tradingmode"), index=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market_type: Mapped[MarketType] = mapped_column(enum_column(MarketType, "markettype"))

    # Inputs
    filters_state: Mapped[dict] = mapped_column(JSON)
    indicators: Mapped[dict] = mapped_column(JSON)
    market_context: Mapped[dict] = mapped_column(JSON)

    # AI outputs
    signal: Mapped[AISignal] = mapped_column(enum_column(AISignal, "aisignal"))
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(Text)
    suggested_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_sl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_tp1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_tp2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_tp3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Action taken
    trade_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    trade_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("trades.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
