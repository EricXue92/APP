"""add booking_invites table and invite notification types

Revision ID: 2e0428fb85f9
Revises: 90f4ed05c37f
Create Date: 2026-04-16 10:05:06.940888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e0428fb85f9'
down_revision: Union[str, Sequence[str], None] = '90f4ed05c37f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing notificationtype enum values (match proposal, chat, event, and booking invite)
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'match_proposal_received'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'match_proposal_accepted'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'match_proposal_rejected'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'match_suggestion'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'new_chat_message'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_registration_open'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_joined'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_started'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_match_ready'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_score_submitted'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_score_confirmed'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_score_disputed'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_walkover'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_eliminated'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_completed'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'event_cancelled'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'booking_invite_received'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'booking_invite_accepted'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'booking_invite_rejected'")

    # Create invitestatus enum (matchtype and genderrequirement already exist)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE invitestatus AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Create booking_invites table using raw SQL to avoid Alembic auto-creating existing enum types
    op.execute("""
        CREATE TABLE booking_invites (
            id UUID NOT NULL,
            inviter_id UUID NOT NULL,
            invitee_id UUID NOT NULL,
            court_id UUID NOT NULL,
            match_type matchtype NOT NULL,
            play_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            gender_requirement genderrequirement NOT NULL,
            cost_per_person INTEGER,
            description TEXT,
            status invitestatus NOT NULL,
            booking_id UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (court_id) REFERENCES courts(id) ON DELETE CASCADE,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS booking_invites")
    op.execute("DROP TYPE IF EXISTS invitestatus")
    # Note: notificationtype enum values cannot be removed in PostgreSQL without recreating the type
