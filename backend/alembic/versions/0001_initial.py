"""Initial schema — create all VOLTAGE tables

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # auth_tokens
    op.create_table('auth_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_auth_tokens'),
    )

    # bot_settings
    op.create_table('bot_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.Enum('real','paper','backtest', name='tradingmode'), nullable=False),
        sa.Column('spot_pairs', sa.JSON(), nullable=True),
        sa.Column('futures_pairs', sa.JSON(), nullable=True),
        sa.Column('spot_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('futures_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('spot_allocated_balance', sa.Float(), nullable=True),
        sa.Column('futures_allocated_balance', sa.Float(), nullable=True),
        sa.Column('paper_initial_balance_spot', sa.Float(), server_default='10000', nullable=False),
        sa.Column('paper_initial_balance_futures', sa.Float(), server_default='10000', nullable=False),
        sa.Column('paper_current_balance_spot', sa.Float(), server_default='10000', nullable=False),
        sa.Column('paper_current_balance_futures', sa.Float(), server_default='10000', nullable=False),
        sa.Column('backtest_start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backtest_end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backtest_initial_balance_spot', sa.Float(), server_default='10000', nullable=False),
        sa.Column('backtest_initial_balance_futures', sa.Float(), server_default='10000', nullable=False),
        sa.Column('risk_per_trade_pct', sa.Float(), server_default='2.0', nullable=False),
        sa.Column('max_open_positions', sa.Integer(), server_default='5', nullable=False),
        sa.Column('max_positions_per_sector', sa.Integer(), server_default='3', nullable=False),
        sa.Column('ai_confidence_threshold', sa.Float(), server_default='0.72', nullable=False),
        sa.Column('default_leverage', sa.Integer(), server_default='3', nullable=False),
        sa.Column('auto_trading_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_bot_settings'),
        sa.UniqueConstraint('mode', name='uq_bot_settings_mode'),
    )

    # backtest_sessions
    op.create_table('backtest_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=True),
        sa.Column('symbols', sa.JSON(), nullable=True),
        sa.Column('market_type', sa.Enum('spot','futures', name='markettype'), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('initial_balance', sa.Float(), nullable=False),
        sa.Column('final_balance', sa.Float(), nullable=True),
        sa.Column('total_trades', sa.Integer(), server_default='0', nullable=False),
        sa.Column('winning_trades', sa.Integer(), server_default='0', nullable=False),
        sa.Column('losing_trades', sa.Integer(), server_default='0', nullable=False),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('profit_factor', sa.Float(), nullable=True),
        sa.Column('max_drawdown', sa.Float(), nullable=True),
        sa.Column('total_pnl', sa.Float(), nullable=True),
        sa.Column('avg_rr', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('progress', sa.Float(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('results_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_backtest_sessions'),
    )
    op.create_index('ix_backtest_sessions_created_at', 'backtest_sessions', ['created_at'])

    # trades
    op.create_table('trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.Enum('real','paper','backtest', name='tradingmode'), nullable=False),
        sa.Column('market_type', sa.Enum('spot','futures', name='markettype'), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('side', sa.Enum('Long','Short','None', name='positionside'), nullable=False),
        sa.Column('status', sa.Enum('open','closed','cancelled', name='tradestatus'), server_default='open', nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('entry_qty', sa.Float(), nullable=False),
        sa.Column('exit_qty', sa.Float(), server_default='0', nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stop_loss_price', sa.Float(), nullable=True),
        sa.Column('take_profit_1_price', sa.Float(), nullable=True),
        sa.Column('take_profit_2_price', sa.Float(), nullable=True),
        sa.Column('take_profit_3_price', sa.Float(), nullable=True),
        sa.Column('tp1_filled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('tp2_filled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('tp3_filled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('trailing_stop_active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('trailing_stop_price', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), server_default='0', nullable=False),
        sa.Column('unrealized_pnl', sa.Float(), server_default='0', nullable=False),
        sa.Column('fees_total', sa.Float(), server_default='0', nullable=False),
        sa.Column('net_pnl', sa.Float(), server_default='0', nullable=False),
        sa.Column('leverage', sa.Integer(), server_default='1', nullable=False),
        sa.Column('ai_signal', sa.Enum('long','short','neutral','wait', name='aisignal'), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('ai_analysis_entry', sa.Text(), nullable=True),
        sa.Column('ai_analysis_exit', sa.Text(), nullable=True),
        sa.Column('ai_conclusion', sa.Text(), nullable=True),
        sa.Column('ai_filters_snapshot', sa.JSON(), nullable=True),
        sa.Column('voltage_filters', sa.JSON(), nullable=True),
        sa.Column('backtest_session_id', sa.Integer(), sa.ForeignKey('backtest_sessions.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_trades'),
    )
    op.create_index('ix_trades_mode', 'trades', ['mode'])
    op.create_index('ix_trades_symbol', 'trades', ['symbol'])
    op.create_index('ix_trades_mode_symbol', 'trades', ['mode', 'symbol'])
    op.create_index('ix_trades_mode_status', 'trades', ['mode', 'status'])
    op.create_index('ix_trades_entry_time', 'trades', ['entry_time'])

    # orders
    op.create_table('orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.Enum('real','paper','backtest', name='tradingmode'), nullable=False),
        sa.Column('market_type', sa.Enum('spot','futures', name='markettype'), nullable=False),
        sa.Column('exchange_order_id', sa.String(100), nullable=True),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('side', sa.Enum('Buy','Sell', name='orderside'), nullable=False),
        sa.Column('order_type', sa.Enum('Market','Limit','StopLoss','TakeProfit','StopLimit','TrailingStop', name='ordertype'), nullable=False),
        sa.Column('status', sa.Enum('Pending','Open','Filled','PartiallyFilled','Cancelled','Rejected','Triggered','Expired', name='orderstatus'), server_default='Pending', nullable=False),
        sa.Column('position_side', sa.Enum('Long','Short','None', name='positionside'), server_default='None', nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('stop_price', sa.Float(), nullable=True),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('filled_qty', sa.Float(), server_default='0', nullable=False),
        sa.Column('avg_fill_price', sa.Float(), nullable=True),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('trades.id'), nullable=True),
        sa.Column('parent_order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('fee', sa.Float(), server_default='0', nullable=False),
        sa.Column('fee_currency', sa.String(10), server_default='USDT', nullable=False),
        sa.Column('ai_signal', sa.Enum('long','short','neutral','wait', name='aisignal'), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('backtest_session_id', sa.Integer(), sa.ForeignKey('backtest_sessions.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_orders'),
    )
    op.create_index('ix_orders_mode', 'orders', ['mode'])
    op.create_index('ix_orders_symbol', 'orders', ['symbol'])
    op.create_index('ix_orders_exchange_order_id', 'orders', ['exchange_order_id'])
    op.create_index('ix_orders_mode_symbol', 'orders', ['mode', 'symbol'])
    op.create_index('ix_orders_mode_status', 'orders', ['mode', 'status'])
    op.create_index('ix_orders_created_at', 'orders', ['created_at'])

    # journal_entries
    op.create_table('journal_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('trades.id'), nullable=False),
        sa.Column('mode', sa.Enum('real','paper','backtest', name='tradingmode'), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('market_type', sa.Enum('spot','futures', name='markettype'), nullable=False),
        sa.Column('side', sa.Enum('Long','Short','None', name='positionside'), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profits', sa.JSON(), nullable=True),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('realized_pnl', sa.Float(), server_default='0', nullable=False),
        sa.Column('fees', sa.Float(), server_default='0', nullable=False),
        sa.Column('net_pnl', sa.Float(), server_default='0', nullable=False),
        sa.Column('pnl_percent', sa.Float(), server_default='0', nullable=False),
        sa.Column('ai_post_analysis', sa.Text(), nullable=True),
        sa.Column('ai_lessons', sa.Text(), nullable=True),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('voltage_snapshot', sa.JSON(), nullable=True),
        sa.Column('chart_data', sa.JSON(), nullable=True),
        sa.Column('user_notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_journal_entries'),
        sa.UniqueConstraint('trade_id', name='uq_journal_entries_trade_id'),
    )
    op.create_index('ix_journal_entries_mode', 'journal_entries', ['mode'])

    # ai_analysis_logs
    op.create_table('ai_analysis_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.Enum('real','paper','backtest', name='tradingmode'), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('market_type', sa.Enum('spot','futures', name='markettype'), nullable=False),
        sa.Column('filters_state', sa.JSON(), nullable=False),
        sa.Column('indicators', sa.JSON(), nullable=False),
        sa.Column('market_context', sa.JSON(), nullable=False),
        sa.Column('signal', sa.Enum('long','short','neutral','wait', name='aisignal'), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('suggested_entry', sa.Float(), nullable=True),
        sa.Column('suggested_sl', sa.Float(), nullable=True),
        sa.Column('suggested_tp1', sa.Float(), nullable=True),
        sa.Column('suggested_tp2', sa.Float(), nullable=True),
        sa.Column('suggested_tp3', sa.Float(), nullable=True),
        sa.Column('trade_opened', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('trade_id', sa.Integer(), sa.ForeignKey('trades.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_ai_analysis_logs'),
    )
    op.create_index('ix_ai_analysis_logs_mode', 'ai_analysis_logs', ['mode'])
    op.create_index('ix_ai_analysis_logs_symbol', 'ai_analysis_logs', ['symbol'])
    op.create_index('ix_ai_analysis_logs_created_at', 'ai_analysis_logs', ['created_at'])

    # market_data_cache
    op.create_table('market_data_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_market_data_cache'),
    )
    op.create_index('ix_market_data_cache_symbol', 'market_data_cache', ['symbol'])
    op.create_index('ix_market_data_cache_timestamp', 'market_data_cache', ['timestamp'])
    op.create_index('ix_market_data_symbol_tf_ts', 'market_data_cache', ['symbol', 'timeframe', 'timestamp'], unique=True)


def downgrade() -> None:
    op.drop_table('market_data_cache')
    op.drop_table('ai_analysis_logs')
    op.drop_table('journal_entries')
    op.drop_table('orders')
    op.drop_table('trades')
    op.drop_table('backtest_sessions')
    op.drop_table('bot_settings')
    op.drop_table('auth_tokens')
    # Drop custom enums
    for enum in ['tradingmode', 'markettype', 'orderside', 'ordertype', 'orderstatus',
                 'positionside', 'tradestatus', 'aisignal']:
        op.execute(f'DROP TYPE IF EXISTS {enum}')
