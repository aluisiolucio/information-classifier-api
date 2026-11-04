"""Fluxo simplificado: análises de origem única e regra global.

Revision ID: 001_simplified
Revises: None
Create Date: 2026-10-23
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from information_classifier_api.domain.entities.classification_rule import (
    DEFAULT_RULE_PROMPT,
)

revision: str = "001_simplified"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classification_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_classification_rule_singleton"),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("input_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rule_prompt", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_media_type", sa.String(length=127), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("usage_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analyses_input_type", "analyses", ["input_type"])
    op.create_index("ix_analyses_status", "analyses", ["status"])
    op.create_index("ix_analyses_status_created", "analyses", ["status", "created_at"])
    _seed_rule()


def _seed_rule() -> None:
    table = sa.table(
        "classification_rule",
        sa.column("id", sa.Integer),
        sa.column("prompt", sa.Text),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": 1,
                "prompt": DEFAULT_RULE_PROMPT,
                "updated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_status_created", table_name="analyses")
    op.drop_index("ix_analyses_status", table_name="analyses")
    op.drop_index("ix_analyses_input_type", table_name="analyses")
    op.drop_table("analyses")
    op.drop_table("classification_rule")
