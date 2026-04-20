"""Add scan interval minutes to bot settings

Revision ID: 0002_add_scan_interval_minutes
Revises: 0001_initial
Create Date: 2026-04-20 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_scan_interval_minutes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bot_settings",
        sa.Column("scan_interval_minutes", sa.Integer(), server_default="15", nullable=False),
    )
    op.execute(
        "UPDATE bot_settings SET scan_interval_minutes = 240 WHERE mode = 'backtest'"
    )


def downgrade() -> None:
    op.drop_column("bot_settings", "scan_interval_minutes")
