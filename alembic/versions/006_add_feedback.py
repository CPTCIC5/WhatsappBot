"""add feedback table

Revision ID: 006
Revises: 005
Create Date: 2026-06-27

Website feedback forum: collects customer experience feedback, optionally tied
to a purchased product.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("experience", sa.String(), nullable=False),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_feedback_name", "feedback", ["name"])
    op.create_index("ix_feedback_phone", "feedback", ["phone"])
    op.create_index("ix_feedback_product_id", "feedback", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_product_id", table_name="feedback")
    op.drop_index("ix_feedback_phone", table_name="feedback")
    op.drop_index("ix_feedback_name", table_name="feedback")
    op.drop_table("feedback")
