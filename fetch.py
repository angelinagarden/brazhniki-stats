#!/usr/bin/env python3
"""
Scrape all posts of @butterflies_and_berliners via public preview t.me/s/<channel>?before=<id>.

Output:
  posts.jsonl   one JSON object per post, sorted by id ascending
  raw_pages/    cached HTML of every fetched page (gitignored)
  fetch.log     progress + warnings

Notes:
  - Public preview exposes: id, date (ISO UTC), text (HTML), views (str like "2.4K"),
    reactions (emoji + count), forwards from, reply-to id, media type.
  - Deleted messages are skipped by Telegram's preview; a gap in ids = deletion.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from html.parser import HTMLParser
from html import unescape

CHANNEL = "butterflies_and_berliners"
BASE = f"https://t.me/s/{CHANNEL}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw_pages"
OUT = HERE / "posts.jsonl"
LOG = HERE / "fetch.log"

RAW_DIR.mkdir(exist_ok=True)


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, file=sys.stderr)
    with LOG.open("a") as f:
        f.write(line + "\n")


def http_get(url: str, retries: int = 5) -> str:
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["curl", "-sSL", "--fail", "--max-time", "30",
                 "-A", UA, "-H", "Accept-Language: ru,en;q=0.9", url],
                capture_output=True, timeout=40,
            )
            if r.returncode == 0 and r.stdout:
                return r.stdout.decode("utf-8", errors="replace")
            err = r.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"curl rc={r.returncode}: {err}")
        except Exception as e:
            wait = 2 ** attempt
            log(f"  HTTP error on {url}: {e} (retry {attempt+1}/{retries} in {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {url}")


# ---------- parsing ----------

@dataclass
class Post:
    id: int
    date: str
    text: str
    text_html: str
    views_raw: str
    views: int
    reactions: dict = field(default_factory=dict)
    forwarded_from: str | None = None
    forwarded_from_url: str | None = None
    reply_to_id: int | None = None
    media_type: str | None = None  # photo | video | voice | document | sticker | poll | link_preview | None
    media_url: str | None = None
    link_preview_url: str | None = None
    edited: bool = False
    is_service: bool = False


def _views_to_int(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    s = s.replace(",", ".")
    m = re.match(r"^([\d.]+)\s*([KMB])?$", s)
    if not m:
        return 0
    num = float(m.group(1))
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(m.group(2) or "", 1)
    return int(num * mult)


class _StripTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buf: list[str] = []

    def handle_data(self, data: str) -> None:
        self.buf.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.buf.append("\n")

    def result(self) -> str:
        return "".join(self.buf)


def _strip_html(s: str) -> str:
    p = _StripTags()
    p.feed(s)
    return p.result()


POST_BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message_wrap[^"]*">(.+?)(?=<div class="tgme_widget_message_wrap|<section class="tgme_channel_history|$)',
    re.DOTALL,
)
DATA_POST_RE = re.compile(r'data-post="([^/]+)/(\d+)"')
TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?=<div class="tgme_widget_message_(?:bottom|reply|forwarded|views|footer|from|service|owner|user|poll|photo|video|document|voice|location|contact|sticker|link_preview|svc|date_meta|info))',
    re.DOTALL,
)
VIEWS_RE = re.compile(r'class="tgme_widget_message_views">([^<]+)<')
DATE_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
REACTION_BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message_reactions[^"]*">(.*?)</div>',
    re.DOTALL,
)
# Each reaction: <span class="tgme_reaction"><i class="emoji"...><b>EMOJI</b></i>COUNT</span>
# Or custom animated: <span class="tgme_reaction"><i class="emoji ..."><b>...</b></i>COUNT</span>
REACTION_ITEM_RE = re.compile(
    r'<span class="tgme_reaction[^"]*">\s*(?:<i[^>]*>(?:<b>([^<]+)</b>|([^<]+))</i>|<tg-emoji[^>]*>([^<]+)</tg-emoji>)?\s*([0-9][0-9.,KMB]*)\s*</span>',
    re.DOTALL,
)
EDITED_RE = re.compile(r'tgme_widget_message_meta[^>]*>.*?edited', re.DOTALL | re.IGNORECASE)
FORWARD_RE = re.compile(
    r'<a class="tgme_widget_message_forwarded_from_name"[^>]*(?:href="([^"]*)")?[^>]*>([^<]+)</a>',
    re.DOTALL,
)
REPLY_RE = re.compile(
    r'<a class="tgme_widget_message_reply[^"]*"[^>]*href="[^/]*/[^/]+/(\d+)"',
)
PHOTO_RE = re.compile(r'tgme_widget_message_photo_wrap[^"]*"\s*href="([^"]+)"\s*style="[^"]*background-image:url\(\'([^\']+)\'')
VIDEO_RE = re.compile(r'tgme_widget_message_video_player[^"]*"[^>]*>.*?<video[^>]*src="([^"]+)"', re.DOTALL)
VOICE_RE = re.compile(r'tgme_widget_message_voice[^"]*"')
STICKER_RE = re.compile(r'tgme_widget_message_sticker[^"]*"')
DOC_RE = re.compile(r'tgme_widget_message_document[^"]*"')
POLL_RE = re.compile(r'tgme_widget_message_poll[^"]*"')
LINK_PREVIEW_RE = re.compile(
    r'<a class="tgme_widget_message_link_preview[^"]*"\s*href="([^"]+)"',
)


def parse_page(html: str) -> list[Post]:
    posts: list[Post] = []
    for m in POST_BLOCK_RE.finditer(html):
        block = m.group(0)
        dm = DATA_POST_RE.search(block)
        if not dm:
            continue
        pid = int(dm.group(2))
        date_m = DATE_RE.search(block)
        if not date_m:
            continue
        views_m = VIEWS_RE.search(block)
        views_raw = views_m.group(1).strip() if views_m else ""

        text_m = TEXT_RE.search(block)
        if text_m:
            text_html = text_m.group(1)
            text = _strip_html(unescape(text_html)).strip()
        else:
            text_html = ""
            text = ""

        # reactions
        reactions: dict[str, int] = {}
        rb = REACTION_BLOCK_RE.search(block)
        if rb:
            for item in REACTION_ITEM_RE.finditer(rb.group(1)):
                emoji = (item.group(1) or item.group(2) or item.group(3) or "?").strip()
                emoji = unescape(emoji)
                count_s = item.group(4).strip()
                reactions[emoji] = reactions.get(emoji, 0) + _views_to_int(count_s)

        fwd_m = FORWARD_RE.search(block)
        fwd_from = unescape(fwd_m.group(2)).strip() if fwd_m else None
        fwd_url = fwd_m.group(1) if fwd_m and fwd_m.group(1) else None

        reply_m = REPLY_RE.search(block)
        reply_to = int(reply_m.group(1)) if reply_m else None

        media_type: str | None = None
        media_url: str | None = None
        if PHOTO_RE.search(block):
            pm = PHOTO_RE.search(block)
            media_type = "photo"
            media_url = pm.group(2) if pm else None
        elif VIDEO_RE.search(block):
            vm = VIDEO_RE.search(block)
            media_type = "video"
            media_url = vm.group(1) if vm else None
        elif VOICE_RE.search(block):
            media_type = "voice"
        elif STICKER_RE.search(block):
            media_type = "sticker"
        elif DOC_RE.search(block):
            media_type = "document"
        elif POLL_RE.search(block):
            media_type = "poll"

        lp_m = LINK_PREVIEW_RE.search(block)
        lp_url = lp_m.group(1) if lp_m else None
        if media_type is None and lp_url:
            media_type = "link_preview"

        edited = bool(EDITED_RE.search(block))

        is_service = 'tgme_widget_message_service' in block[:400]

        posts.append(Post(
            id=pid,
            date=date_m.group(1),
            text=text,
            text_html=text_html,
            views_raw=views_raw,
            views=_views_to_int(views_raw),
            reactions=reactions,
            forwarded_from=fwd_from,
            forwarded_from_url=fwd_url,
            reply_to_id=reply_to,
            media_type=media_type,
            media_url=media_url,
            link_preview_url=lp_url,
            edited=edited,
            is_service=is_service,
        ))
    return posts


def parse_channel_meta(html: str) -> dict:
    out: dict = {}
    for cm in re.finditer(
        r'<div class="tgme_channel_info_counter">\s*<span class="counter_value">([^<]+)</span>\s*<span class="counter_type">([^<]+)</span>',
        html,
    ):
        out[cm.group(2)] = cm.group(1)
    title_m = re.search(r'<div class="tgme_channel_info_header_title[^"]*"><span[^>]*>([^<]+)</span>', html)
    if title_m:
        out["title"] = unescape(title_m.group(1))
    desc_m = re.search(r'<div class="tgme_channel_info_description[^"]*">(.*?)</div>', html, re.DOTALL)
    if desc_m:
        out["description"] = _strip_html(unescape(desc_m.group(1))).strip()
    return out


def main() -> int:
    all_posts: dict[int, Post] = {}
    channel_meta: dict = {}

    # First page = latest
    log(f"GET {BASE}")
    html = http_get(BASE)
    (RAW_DIR / "page_latest.html").write_text(html)
    channel_meta = parse_channel_meta(html)
    log(f"channel meta: {channel_meta}")
    posts = parse_page(html)
    log(f"first page: {len(posts)} posts, ids {posts[0].id if posts else '-'}..{posts[-1].id if posts else '-'}")
    for p in posts:
        all_posts[p.id] = p

    if not posts:
        log("no posts on first page — abort")
        return 1

    # Paginate backward
    cursor = min(p.id for p in posts)
    stuck_at = None
    while True:
        url = f"{BASE}?before={cursor}"
        log(f"GET before={cursor}")
        html = http_get(url)
        (RAW_DIR / f"page_before_{cursor}.html").write_text(html)
        new_posts = parse_page(html)
        if not new_posts:
            log("empty page — reached top of channel")
            break
        new_min = min(p.id for p in new_posts)
        new_max = max(p.id for p in new_posts)
        added = 0
        for p in new_posts:
            if p.id not in all_posts:
                all_posts[p.id] = p
                added += 1
        log(f"page ids {new_min}..{new_max}  added={added}  total={len(all_posts)}")

        # Advance cursor
        if new_min >= cursor:
            if stuck_at == cursor:
                log(f"cursor stuck at {cursor} twice — stop")
                break
            stuck_at = cursor
            cursor = new_min
        else:
            stuck_at = None
            cursor = new_min

        # Reached id=1 or 2 → done
        if new_min <= 2:
            log("reached beginning of channel")
            break

        time.sleep(0.5)  # polite

    # Write output
    ordered = sorted(all_posts.values(), key=lambda p: p.id)
    with OUT.open("w") as f:
        for p in ordered:
            f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")

    # Also write channel meta
    (HERE / "channel.json").write_text(
        json.dumps(channel_meta, ensure_ascii=False, indent=2)
    )

    log(f"done: {len(ordered)} posts written to {OUT}")
    log(f"id range: {ordered[0].id}..{ordered[-1].id}  "
        f"expected max ~{ordered[-1].id}  "
        f"missing in range (deleted): {ordered[-1].id - ordered[0].id + 1 - len(ordered)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
