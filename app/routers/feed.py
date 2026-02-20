from fastapi import APIRouter, Request
from fastapi.responses import Response
from datetime import datetime
from app.services.posts import get_all_posts
from app.config import settings

router = APIRouter()

def _build_rss(request: Request) -> str:
    posts = get_all_posts()
    site_url = settings.site_url

    items = ""
    for post in posts:
        url = f"{site_url}/post/{post.slug}"
        pub_date = datetime(
            post.date.year,
            post.date.month,
            post.date.day
        ).strftime("%a, %d %b %Y 00:00:00+0000")

        items += f"""
        <item>
            <title>{post.title}</title>
            <link>{url}</link>
            <guid isPermaLink="true">{url}</guid>
            <pubDate>{pub_date}</pubDate>
            <description>{post.summary}</description>
        </item>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>{settings.app_title}</title>
        <link>{site_url}</link>
        <description>{settings.site_description}</description>
        <language>en-us</language>
        <managingEditor>{settings.site_author}</managingEditor>
        <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S+0000")}</lastBuildDate>
        {items}
    </channel>
</rss>"""

@router.get("/feed.xml")
async def rss_feed(request: Request):
    xml = _build_rss(request)
    return Response(content=xml, media_type="application/rss+xml")
