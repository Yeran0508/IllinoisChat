"""Add document storage and embedding provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0002"
down_revision: str | None = "20261109_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("storage_key", sa.String(length=1000), nullable=True),
    )
    op.execute(
        "UPDATE document_versions "
        "SET storage_key = concat(id::text, '/legacy-source') "
        "WHERE storage_key IS NULL"
    )
    op.alter_column("document_versions", "storage_key", nullable=False)
    op.add_column(
        "document_versions",
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "embedding_model")
    op.drop_column("document_versions", "storage_key")
