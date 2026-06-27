"""add product_images table and blog image_blob column

Revision ID: 008
Revises: 007
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("blob_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    op.add_column("blogs", sa.Column("image_blob", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("blogs", "image_blob")
    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_table("product_images")
