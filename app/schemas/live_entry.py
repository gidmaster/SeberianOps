from dataclasses import dataclass
from datetime import datetime
from app.database.models.live_entry import LiveEntry

@dataclass
class LiveEntryView:
    id: int
    body: str
    body_html: str
    pinned: bool
    created_at: datetime

    @classmethod
    def from_model(cls, entry: LiveEntry, rendered: str) -> "LiveEntryView":
        return cls(
            id=entry.id,
            body=entry.body,
            body_html=rendered,
            pinned=entry.pinned,
            created_at=entry.created_at,
        )
