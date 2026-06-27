"""add categories, reviews, blogs (+ product<->category m2m)

Revision ID: 007
Revises: 006
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Categories
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_index("ix_categories_name", "categories", ["name"])

    # Product <-> Category many-to-many
    op.create_table(
        "product_categories",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), primary_key=True),
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_reviews_product_id", "reviews", ["product_id"])

    # Blogs
    op.create_table(
        "blogs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("heading", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_blogs_heading", "blogs", ["heading"])


def downgrade() -> None:
    op.drop_index("ix_blogs_heading", table_name="blogs")
    op.drop_table("blogs")
    op.drop_index("ix_reviews_product_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("product_categories")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
