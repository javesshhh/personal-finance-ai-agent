"""add_sessions_and_session_id_to_transactions

Revision ID: 22107c598e4a
Revises: 3fe1e00972bd
Create Date: 2026-04-26 11:10:46.811440

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '22107c598e4a'
down_revision: Union[str, Sequence[str], None] = '3fe1e00972bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_SESSION_NAME = "default"


def upgrade() -> None:
    # 1. Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 2. Insert the default session so existing transactions can be backfilled
    op.execute(
        sa.text(f"INSERT INTO sessions (id, name) VALUES ('{DEFAULT_SESSION_ID}'::uuid, '{DEFAULT_SESSION_NAME}')")
    )

    # 3. Add session_id as nullable first so existing rows don't violate NOT NULL
    op.add_column("transactions", sa.Column("session_id", sa.UUID(), nullable=True))

    # 4. Backfill all existing transactions to the default session
    op.execute(
        sa.text(f"UPDATE transactions SET session_id = '{DEFAULT_SESSION_ID}'::uuid WHERE session_id IS NULL")
    )

    # 5. Now enforce NOT NULL
    op.alter_column("transactions", "session_id", nullable=False)

    # 6. Swap unique constraint to include session_id
    op.drop_constraint("uq_transaction_date_description_amount", "transactions", type_="unique")
    op.create_unique_constraint(
        "uq_transaction_session_date_description_amount",
        "transactions",
        ["session_id", "date", "description", "amount"],
    )

    # 7. Add FK
    op.create_foreign_key(
        "fk_transactions_session_id",
        "transactions",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_session_id", "transactions", type_="foreignkey")
    op.drop_constraint("uq_transaction_session_date_description_amount", "transactions", type_="unique")
    op.create_unique_constraint(
        "uq_transaction_date_description_amount",
        "transactions",
        ["date", "description", "amount"],
    )
    op.drop_column("transactions", "session_id")
    op.drop_table("sessions")
