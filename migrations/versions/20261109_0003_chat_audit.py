"""Add privacy-preserving chat request audit logs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261109_0003"
down_revision: str | None = "20261109_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_code", sa.String(length=64), nullable=False),
        sa.Column("query_sha256", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("refusal_reason", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB(), nullable=False),
        sa.Column("cited_chunk_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latency_ms >= 0", name=op.f("ck_chat_request_logs_latency_nonnegative")
        ),
        sa.CheckConstraint(
            "outcome IN ('answered', 'refused', 'model_error')",
            name=op.f("ck_chat_request_logs_valid_outcome"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_request_logs")),
    )
    op.create_index(
        op.f("ix_chat_request_logs_course_code"),
        "chat_request_logs",
        ["course_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_request_logs_course_code"), table_name="chat_request_logs")
    op.drop_table("chat_request_logs")
