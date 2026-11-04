from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClassificationRuleModel(Base):
    __tablename__ = "classification_rule"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_classification_rule_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    prompt: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
