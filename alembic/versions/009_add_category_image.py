"""add image_blob to categories

Revision ID: 009
Revises: 008
Create Date: 2026-07-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("image_blob", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("categories", "image_blob")
