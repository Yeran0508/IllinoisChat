"""Add protected assignment classification for M3 safety."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261110_0004"
down_revision: str | None = "20261109_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "is_protected",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "is_protected")
