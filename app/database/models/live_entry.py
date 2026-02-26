from datetime import datetime
from sqlalchemy import Text, Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class LiveEntry(Base):
    __tablename__ = "live_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<LiveEntry id{self.id} created_at={self.created_at}>"
