from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.live_entry import LiveEntry


class LiveEntryRepository:
    
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, body: str, pinned: bool = False) -> LiveEntry:
        entry = LiveEntry(body=body, pinned=pinned)
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry
    
    async def get_all(self, limit: int = 50, offset: int = 0) -> list[LiveEntry]:
        result = await self.db.execute(
            select(LiveEntry)
            .order_by(LiveEntry.pinned.desc(), LiveEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def count(self) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(LiveEntry)
        )
        return result.scalar_one()
    
    async def delete(self, entry_id: int) -> bool:
        result = await self.db.execute(
            select(LiveEntry).where(LiveEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True

    async def toggle_pin(self, entry_id: int) -> LiveEntry | None:
        result = await self.db.execute(
            select(LiveEntry).where(LiveEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None
        entry.pinned = not entry.pinned
        await self.db.commit()
        await self.db.refresh(entry)
        return entry
    