from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.database.models.post_stat import PostStat

class PostStatRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_slug(self, slug: str) -> PostStat | None:
        result = await self.db.execute(
            select(PostStat).where(PostStat.slug == slug)
        )
        return result.scalar_one_or_none()

    async def increment_view(self, slug: str) -> PostStat:
        stat = await self.get_by_slug(slug)
        now = datetime.now(timezone.utc)        

        if stat is None:
            stat = PostStat(
                slug=slug,
                view_count=1,
                first_viewed_at=now,
                last_viewed_at=now,
            )
            self.db.add(stat)
        else:
            stat.view_count += 1
            stat.last_viewed_at = now

        await self.db.commit()
        await self.db.refresh(stat)
        return stat

    async def get_all_stats(self) -> list[PostStat]:
        result = await self.db.execute(
            select(PostStat).order_by(PostStat.view_count.desc())
        )
        return list(result.scalars().all())
