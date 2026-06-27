"""add referrals table and lead onboarding/referral fields

Revision ID: 005
Revises: 004
Create Date: 2026-06-17

Milestone 3: onboarding state + referral codes on leads, and a referrals
table supporting referral chains (referrals from referrals).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Lead: onboarding + referral fields ---
    op.add_column(
        "leads",
        sa.Column(
            "onboarding_state",
            sa.String(),
            nullable=False,
            server_default="new",
        ),
    )
    op.add_column("leads", sa.Column("referral_code", sa.String(), nullable=True))
    op.add_column("leads", sa.Column("pending_intent", sa.String(), nullable=True))
    with op.batch_alter_table("leads") as batch_op:
        batch_op.create_index("ix_leads_referral_code", ["referral_code"], unique=True)

    # --- Referrals table ---
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("referred_lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("referred_phone", sa.String(), nullable=True),
        sa.Column("referred_name", sa.String(), nullable=True),
        sa.Column("referral_code", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("parent_referral_id", sa.Integer(), sa.ForeignKey("referrals.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])
    op.create_index("ix_referrals_referred_lead_id", "referrals", ["referred_lead_id"])
    op.create_index("ix_referrals_referred_phone", "referrals", ["referred_phone"])
    op.create_index("ix_referrals_referral_code", "referrals", ["referral_code"])
    op.create_index("ix_referrals_parent_referral_id", "referrals", ["parent_referral_id"])


def downgrade() -> None:
    op.drop_index("ix_referrals_parent_referral_id", table_name="referrals")
    op.drop_index("ix_referrals_referral_code", table_name="referrals")
    op.drop_index("ix_referrals_referred_phone", table_name="referrals")
    op.drop_index("ix_referrals_referred_lead_id", table_name="referrals")
    op.drop_index("ix_referrals_referrer_id", table_name="referrals")
    op.drop_table("referrals")

    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_referral_code")
    op.drop_column("leads", "pending_intent")
    op.drop_column("leads", "referral_code")
    op.drop_column("leads", "onboarding_state")
