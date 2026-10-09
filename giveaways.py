#!/usr/bin/env python3
"""
Detect channel-initiated giveaways in posts_cat.jsonl and emit giveaways.json.

Markers are strict — only clear "we are giving away tickets" posts:
  - "розыгрыш" (and inflections)
  - "разыгрываем / разыграем / разыгрывают" (1st+3rd person plural verb)
  - "дарим N билетов / билеты / подарки"
  - "раздаём билеты / приглашения / подарки"

Casual "призы" / "конкурс" / "выиграй" mentions ARE EXCLUDED — they tend to
be event descriptions ("there will be prizes at the venue") rather than
giveaways by the channel.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSTS = HERE / "posts_cat.jsonl"
OUT = HERE / "giveaways.json"

PATTERNS = [
    r"\bрозыгрыш",
    r"разыгрыва[еюя]",
    r"\bразыграем\b",
    r"ночной\s+розыгрыш",
    r"\bдарим\s+(?:\d+|билет|подарк|приглас)",
    r"раздаём\s+(?:билет|подарк|приглас)",
]
GIVEAWAY_RE = re.compile("|".join(PATTERNS), re.I)


def is_giveaway(post: dict) -> bool:
    return bool(GIVEAWAY_RE.search(post.get("text", "")))


def month_key(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d.year}-{d.month:02d}"


def iso_week_key(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def main() -> int:
    posts = [json.loads(l) for l in POSTS.open()]
    giveaways = [p for p in posts if is_giveaway(p)]
    non = [p for p in posts if not is_giveaway(p)]

    by_cat = Counter(p["primary_category"] for p in giveaways)
    by_month = Counter(month_key(p["date"]) for p in giveaways)
    by_week = Counter(iso_week_key(p["date"]) for p in giveaways)

    g_views = [p["views"] for p in giveaways]
    g_rx = [p["rx_sum"] for p in giveaways]
    n_views = [p["views"] for p in non]
    n_rx = [p["rx_sum"] for p in non]

    # Burst detection — consecutive giveaway posts within 7 days
    sorted_g = sorted(giveaways, key=lambda p: p["date"])
    bursts = []
    cur: list[dict] = []
    for p in sorted_g:
        if not cur:
            cur = [p]
            continue
        last_d = datetime.fromisoformat(cur[-1]["date"].replace("Z", "+00:00"))
        this_d = datetime.fromisoformat(p["date"].replace("Z", "+00:00"))
        if (this_d - last_d).days <= 3:
            cur.append(p)
        else:
            if len(cur) >= 3:
                bursts.append({
                    "start": cur[0]["date"][:10],
                    "end": cur[-1]["date"][:10],
                    "n": len(cur),
                    "ids": [p["id"] for p in cur],
                    "total_views": sum(p["views"] for p in cur),
                    "total_rx": sum(p["rx_sum"] for p in cur),
                })
            cur = [p]
    if len(cur) >= 3:
        bursts.append({
            "start": cur[0]["date"][:10],
            "end": cur[-1]["date"][:10],
            "n": len(cur),
            "ids": [p["id"] for p in cur],
            "total_views": sum(p["views"] for p in cur),
            "total_rx": sum(p["rx_sum"] for p in cur),
        })

    data = {
        "total": len(giveaways),
        "total_posts": len(posts),
        "share_pct": round(len(giveaways) / len(posts) * 100, 1),
        "by_category": dict(by_cat),
        "by_month": dict(sorted(by_month.items())),
        "by_week": dict(sorted(by_week.items())),
        "views": {
            "giveaway_avg": round(statistics.mean(g_views)),
            "giveaway_median": round(statistics.median(g_views)),
            "giveaway_max": max(g_views),
            "giveaway_total": sum(g_views),
            "other_avg": round(statistics.mean(n_views)),
            "other_median": round(statistics.median(n_views)),
        },
        "reactions": {
            "giveaway_avg": round(statistics.mean(g_rx), 1),
            "giveaway_total": sum(g_rx),
            "other_avg": round(statistics.mean(n_rx), 1),
        },
        "bursts": bursts,
        "top5_by_views": [
            {
                "id": p["id"],
                "date": p["date"][:10],
                "views": p["views"],
                "rx": p["rx_sum"],
                "cat": p["primary_category"],
                "text": p["text"][:200] + ("…" if len(p["text"]) > 200 else ""),
            }
            for p in sorted(giveaways, key=lambda p: -p["views"])[:5]
        ],
        "top5_by_reactions": [
            {
                "id": p["id"],
                "date": p["date"][:10],
                "views": p["views"],
                "rx": p["rx_sum"],
                "cat": p["primary_category"],
                "text": p["text"][:200] + ("…" if len(p["text"]) > 200 else ""),
            }
            for p in sorted(giveaways, key=lambda p: -p["rx_sum"])[:5]
        ],
        "all": [
            {
                "id": p["id"],
                "date": p["date"][:10],
                "views": p["views"],
                "rx": p["rx_sum"],
                "cat": p["primary_category"],
                "text": p["text"][:160] + ("…" if len(p["text"]) > 160 else ""),
            }
            for p in sorted(giveaways, key=lambda p: p["date"])
        ],
    }

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"wrote {OUT.name}")
    print(f"  total giveaways: {data['total']} ({data['share_pct']}% of posts)")
    print(f"  by category: {data['by_category']}")
    print(f"  bursts (>=3 in 3 days): {len(bursts)}")
    for b in bursts:
        print(f"    {b['start']}..{b['end']}: {b['n']} posts, {b['total_views']} views")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
