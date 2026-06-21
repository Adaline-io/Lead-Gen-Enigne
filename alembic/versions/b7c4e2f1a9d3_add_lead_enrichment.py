"""add lead enrichment

Revision ID: b7c4e2f1a9d3
Revises: 1da8ea9487ef
Create Date: 2026-06-21 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c4e2f1a9d3'
down_revision: str | None = '1da8ea9487ef'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enrichment', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('enrichment')
