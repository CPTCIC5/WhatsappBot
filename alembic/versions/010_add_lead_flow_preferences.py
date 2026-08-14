"""add lead flow_stage and occasion/budget preferences from template flow

Revision ID: 010
Revises: 50a4fec6594a
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, Sequence[str], None] = "50a4fec6594a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("flow_stage", sa.String(), nullable=True))
    op.add_column("leads", sa.Column("occasion", sa.String(), nullable=True))
    op.add_column("leads", sa.Column("budget_label", sa.String(), nullable=True))
    op.add_column("leads", sa.Column("budget_min", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("budget_max", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "budget_max")
    op.drop_column("leads", "budget_min")
    op.drop_column("leads", "budget_label")
    op.drop_column("leads", "occasion")
    op.drop_column("leads", "flow_stage")
