import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CreditReason(str, enum.Enum):
    ATTENDED = "attended"
    FIRST_CANCEL_WARNING = "first_cancel_warning"
    CANCEL_24H = "cancel_24h"
    CANCEL_12_24H = "cancel_12_24h"
    CANCEL_2H = "cancel_2h"
    NO_SHOW = "no_show"
    WEATHER_CANCEL = "weather_cancel"
    ADMIN_ADJUST = "admin_adjust"


class CreditLog(Base):
    __tablename__ = "credit_logs"
    __table_args__ = (Index("ix_credit_logs_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[CreditReason] = mapped_column(Enum(CreditReason))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
