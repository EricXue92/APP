"""add is_ideal_player and notification enum values

Revision ID: 123488eefd6c
Revises: 84f2939410f0
Create Date: 2026-04-15 00:29:43.127189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '123488eefd6c'
down_revision: Union[str, Sequence[str], None] = '84f2939410f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_ideal_player', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ideal_player_gained'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ideal_player_lost'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_ideal_player')
    # Note: PostgreSQL does not support removing enum values; left as-is
