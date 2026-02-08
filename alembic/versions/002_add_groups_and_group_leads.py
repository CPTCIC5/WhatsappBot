"""add groups and group_leads

Revision ID: 002
Revises: 001
Create Date: 2025-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_groups_id"), "groups", ["id"], unique=False)
    op.create_index(op.f("ix_groups_name"), "groups", ["name"], unique=False)

    op.create_table(
        "group_leads",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("group_id", "lead_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("group_leads")
    op.drop_index(op.f("ix_groups_name"), table_name="groups")
    op.drop_index(op.f("ix_groups_id"), table_name="groups")
    op.drop_table("groups")
