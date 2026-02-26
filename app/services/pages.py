import os
import yaml
import markdown2
from dataclasses import dataclass

PAGES_DIR = "content/pages"

@dataclass
class Page:
    title: str
    content_html: str

def get_page(slug: str) -> Page | None:
    filepath = os.path.join(PAGES_DIR, f"{slug}.md")
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    _, frontmatter, body = raw.split("---", 2)
    meta = yaml.safe_load(frontmatter)
    content_html = markdown2.markdown(
        body,
        extras={
            "fenced-code-blocks": {"cssclass": "highlight"},
            "tables": None,
        }
    )

    return Page(title=meta["title"], content_html=content_html)
