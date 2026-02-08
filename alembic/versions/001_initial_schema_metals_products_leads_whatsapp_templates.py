"""initial schema: metals, products, leads, whatsapp_templates

Revision ID: 001
Revises:
Create Date: 2025-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "metals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metal", sa.String(), nullable=True),
        sa.Column("karat", sa.String(), nullable=True),
        sa.Column("rate_per_gram", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metals_id"), "metals", ["id"], unique=False)
    op.create_index(op.f("ix_metals_karat"), "metals", ["karat"], unique=False)
    op.create_index(op.f("ix_metals_metal"), "metals", ["metal"], unique=False)

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "tag",
            sa.Enum("new", "existing", name="lead_tags", create_constraint=False),
            nullable=True,
        ),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_leads_email"), "leads", ["email"], unique=True)
    op.create_index(op.f("ix_leads_id"), "leads", ["id"], unique=False)
    op.create_index(op.f("ix_leads_name"), "leads", ["name"], unique=False)
    op.create_index(op.f("ix_leads_phone"), "leads", ["phone"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("style_no", sa.String(), nullable=True),
        sa.Column("jewel_code", sa.String(), nullable=True),
        sa.Column("gross_weight", sa.Float(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metal_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["metal_id"], ["metals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(op.f("ix_products_jewel_code"), "products", ["jewel_code"], unique=False)
    op.create_index(op.f("ix_products_metal_id"), "products", ["metal_id"], unique=False)
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=False)
    op.create_index(op.f("ix_products_style_no"), "products", ["style_no"], unique=False)

    op.create_table(
        "whatsapp_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "MARKETING",
                "UTILITY",
                "AUTHENTICATION",
                name="whatsapp_template_category",
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("use_case", sa.String(), nullable=False),
        sa.Column("components_schema", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "APPROVED",
                "PENDING",
                "REJECTED",
                name="whatsapp_template_status",
                create_constraint=False,
            ),
            nullable=True,
        ),
        sa.Column("meta_template_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_whatsapp_templates_id"), "whatsapp_templates", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_whatsapp_templates_template_name"),
        "whatsapp_templates",
        ["template_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_whatsapp_templates_use_case"),
        "whatsapp_templates",
        ["use_case"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_whatsapp_templates_use_case"), table_name="whatsapp_templates")
    op.drop_index(
        op.f("ix_whatsapp_templates_template_name"), table_name="whatsapp_templates"
    )
    op.drop_index(op.f("ix_whatsapp_templates_id"), table_name="whatsapp_templates")
    op.drop_table("whatsapp_templates")

    op.drop_index(op.f("ix_products_style_no"), table_name="products")
    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_index(op.f("ix_products_metal_id"), table_name="products")
    op.drop_index(op.f("ix_products_jewel_code"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")

    op.drop_index(op.f("ix_leads_phone"), table_name="leads")
    op.drop_index(op.f("ix_leads_name"), table_name="leads")
    op.drop_index(op.f("ix_leads_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_table("leads")

    op.drop_index(op.f("ix_metals_metal"), table_name="metals")
    op.drop_index(op.f("ix_metals_karat"), table_name="metals")
    op.drop_index(op.f("ix_metals_id"), table_name="metals")
    op.drop_table("metals")
