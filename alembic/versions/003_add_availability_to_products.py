"""add availability to products

Revision ID: 003
Revises: 002
Create Date: 2025-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add availability boolean column to products."""
    # Use text("1") so SQLite gets a valid default for existing rows
    op.add_column(
        "products",
        sa.Column("availability", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    """Remove availability column from products."""
    op.drop_column("products", "availability")
