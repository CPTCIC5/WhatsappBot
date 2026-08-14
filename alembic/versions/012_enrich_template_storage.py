"""enrich template_storage for reusable Meta templates

Revision ID: 012
Revises: 011
Create Date: 2026-08-14
"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, Sequence[str], None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("template_storage", sa.Column("slug", sa.String(), nullable=True))
    op.add_column(
        "template_storage",
        sa.Column("language_code", sa.String(), nullable=False, server_default="en_US"),
    )
    op.add_column("template_storage", sa.Column("header_image_blob", sa.String(), nullable=True))
    op.add_column("template_storage", sa.Column("header_media_url", sa.String(), nullable=True))
    op.add_column(
        "template_storage",
        sa.Column("header_media_type", sa.String(), nullable=False, server_default="image"),
    )
    op.add_column("template_storage", sa.Column("body_parameters", sa.JSON(), nullable=True))
    op.add_column(
        "template_storage",
        sa.Column("use_named_parameters", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "template_storage",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_template_storage_slug", "template_storage", ["slug"], unique=True)

    seeds = [
        {
            "slug": "welcome",
            "template_name": "welcome_template_v1",
            "template_note": "First-contact welcome. Body var {name} is filled from the lead.",
            "header_media_url": "https://i.imgur.com/RYBkxXL.jpeg",
            "body_parameters": {"name": "{first_name}"},
        },
        {
            "slug": "occasion",
            "template_name": "occasion_template",
            "template_note": "Onboarding step 2 — pick an occasion.",
            "header_media_url": None,
            "body_parameters": None,
        },
        {
            "slug": "budget",
            "template_name": "budget_template",
            "template_note": "Onboarding step 3 — pick a budget range.",
            "header_media_url": None,
            "body_parameters": None,
        },
        {
            "slug": "trust",
            "template_name": "trust_template_v1",
            "template_note": "Onboarding step 4 — see collection or handbook.",
            "header_media_url": None,
            "body_parameters": None,
        },
        {
            "slug": "category",
            "template_name": "category_template_v1",
            "template_note": "Onboarding step 5 — pick a product category.",
            "header_media_url": None,
            "body_parameters": None,
        },
    ]

    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id, template_name, slug FROM template_storage")
    ).mappings().all()
    by_slug = {row["slug"]: row["id"] for row in existing if row["slug"]}
    by_name = {row["template_name"]: row["id"] for row in existing}

    templates = sa.table(
        "template_storage",
        sa.column("slug", sa.String),
        sa.column("template_name", sa.String),
        sa.column("template_note", sa.Text),
        sa.column("language_code", sa.String),
        sa.column("header_media_url", sa.String),
        sa.column("header_media_type", sa.String),
        sa.column("body_parameters", sa.JSON),
        sa.column("use_named_parameters", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    to_insert = []
    for seed in seeds:
        if seed["slug"] in by_slug:
            continue
        existing_id = by_name.get(seed["template_name"])
        if existing_id:
            conn.execute(
                sa.text(
                    """
                    UPDATE template_storage
                    SET slug = :slug,
                        template_note = COALESCE(template_note, :template_note),
                        header_media_url = COALESCE(header_media_url, :header_media_url),
                        body_parameters = COALESCE(body_parameters, CAST(:body_parameters AS json)),
                        is_active = true
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing_id,
                    "slug": seed["slug"],
                    "template_note": seed["template_note"],
                    "header_media_url": seed["header_media_url"],
                    "body_parameters": json.dumps(seed["body_parameters"])
                    if seed["body_parameters"] is not None
                    else None,
                },
            )
            continue
        to_insert.append(
            {
                "slug": seed["slug"],
                "template_name": seed["template_name"],
                "template_note": seed["template_note"],
                "language_code": "en_US",
                "header_media_url": seed["header_media_url"],
                "header_media_type": "image",
                "body_parameters": seed["body_parameters"],
                "use_named_parameters": True,
                "is_active": True,
            }
        )
    if to_insert:
        op.execute(templates.insert().values(to_insert))


def downgrade() -> None:
    op.drop_index("ix_template_storage_slug", table_name="template_storage")
    op.drop_column("template_storage", "is_active")
    op.drop_column("template_storage", "use_named_parameters")
    op.drop_column("template_storage", "body_parameters")
    op.drop_column("template_storage", "header_media_type")
    op.drop_column("template_storage", "header_media_url")
    op.drop_column("template_storage", "header_image_blob")
    op.drop_column("template_storage", "language_code")
    op.drop_column("template_storage", "slug")
