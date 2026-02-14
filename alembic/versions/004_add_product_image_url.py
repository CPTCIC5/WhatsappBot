"""add product image_url

Revision ID: 004
Revises: bfc97d0343bd
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "bfc97d0343bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "image_url")
