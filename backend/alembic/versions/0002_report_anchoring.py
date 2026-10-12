"""add report anchoring columns (Phase 6: Polygon Amoy)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("anchor_status", sa.String(length=16), nullable=True))
    op.add_column("reports", sa.Column("anchor_tx_hash", sa.String(length=80), nullable=True))
    op.add_column("reports", sa.Column("anchor_block_number", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "anchored_at")
    op.drop_column("reports", "anchor_block_number")
    op.drop_column("reports", "anchor_tx_hash")
    op.drop_column("reports", "anchor_status")
