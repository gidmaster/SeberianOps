from fastapi import APIRouter, Request
from fastapi.responses import Response
from datetime import timezone
from app.services.posts import get_all_posts
from app.config import settings

router = APIRouter()


@router.get("/robots.txt", include_in_schema=False)
async def robots():
    content = f"""User-agent: *
Allow: /
Disallow: /admin

Sitemap: {settings.site_url}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    posts = get_all_posts()
    site_url = settings.site_url.rstrip("/")

    # Static pages that should always be in the sitemap
    static_urls = [
        {"loc": site_url, "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{site_url}/about", "priority": "0.5", "changefreq": "monthly"},
        {"loc": f"{site_url}/live", "priority": "0.6", "changefreq": "daily"},
    ]

    post_urls = [
        {
            "loc": f"{site_url}/post/{post.slug}",
            "lastmod": post.date.isoformat(),
            "priority": "0.8",
            "changefreq": "monthly",
        }
        for post in posts
    ]

    all_urls = static_urls + post_urls

    url_entries = ""
    for url in all_urls:
        lastmod_line = f"\n        <lastmod>{url['lastmod']}</lastmod>" if "lastmod" in url else ""
        url_entries += f"""
    <url>
        <loc>{url['loc']}</loc>{lastmod_line}
        <changefreq>{url['changefreq']}</changefreq>
        <priority>{url['priority']}</priority>
    </url>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{url_entries}
</urlset>"""

    return Response(content=xml, media_type="application/xml")
