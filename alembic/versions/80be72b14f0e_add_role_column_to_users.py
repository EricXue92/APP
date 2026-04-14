"""add role column to users

Revision ID: 80be72b14f0e
Revises: b249196993f8
Create Date: 2026-04-14 15:18:19.364254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80be72b14f0e'
down_revision: Union[str, Sequence[str], None] = 'b249196993f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


userrole_enum = sa.Enum('USER', 'ADMIN', 'SUPERADMIN', name='userrole')


def upgrade() -> None:
    """Upgrade schema."""
    userrole_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column('role', userrole_enum, nullable=False, server_default='USER'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
    userrole_enum.drop(op.get_bind(), checkfirst=True)
