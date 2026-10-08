#!/usr/bin/env python3
"""
Apply LLM-based classification from /tmp/posts_classified.json to posts.jsonl →
posts_cat.jsonl + cat_stats.json. Replaces the keyword classify.py output.

Expected shape of posts_classified.json:
  [{"id": int, "primary": "<cat>", "secondary": ["<cat>", ...]}]
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSTS = HERE / "posts.jsonl"
LLM = Path("/tmp/posts_classified.json")
OUT = HERE / "posts_cat.jsonl"
STATS = HERE / "cat_stats.json"

# New 12-category taxonomy
PRIORITY = [
    "digest",
    "music_classical",
    "music_concert",
    "club_party",
    "cinema",
    "theatre_dance",
    "exhibitions",
    "lectures_talks",
    "food_market",
    "outdoor_sports",
    "community_meta",
    "other",
]

RU_LABELS = {
    "digest":          "дайджесты недели",
    "music_classical": "классика / опера / джаз",
    "music_concert":   "концерты (rock / indie / pop)",
    "club_party":      "клубы / техно / вечеринки",
    "cinema":          "кино",
    "theatre_dance":   "театр / танец / перформанс",
    "exhibitions":     "выставки / музеи",
    "lectures_talks":  "лекции / талки",
    "food_market":     "еда / маркеты",
    "outdoor_sports":  "улица / спорт / природа",
    "community_meta":  "канал / мета",
    "other":           "прочее",
}


def main() -> int:
    posts = [json.loads(l) for l in POSTS.open()]
    posts = [p for p in posts if p.get("views", 0) > 0 and not p.get("is_service")]
    posts.sort(key=lambda p: p["id"])

    llm = {entry["id"]: entry for entry in json.load(LLM.open())}
    missing = [p["id"] for p in posts if p["id"] not in llm]
    if missing:
        print(f"WARN: {len(missing)} posts missing from LLM output: {missing[:10]}")

    for p in posts:
        meta = llm.get(p["id"], {"primary": "other", "secondary": []})
        p["primary_category"] = meta["primary"]
        p["categories"] = [meta["primary"]] + list(meta.get("secondary", []))
        p["cat_scores"] = {}  # LLM doesn't return scores
        p["rx_sum"] = sum(p["reactions"].values())
        p["engagement"] = (p["rx_sum"] / p["views"]) if p["views"] else 0

    with OUT.open("w") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Aggregate
    stats = {"total_posts": len(posts), "categories": {}}
    for cat in PRIORITY:
        bucket = [p for p in posts if p["primary_category"] == cat]
        if not bucket:
            stats["categories"][cat] = {"label": RU_LABELS[cat], "count": 0, "share": 0.0}
            continue
        views = [p["views"] for p in bucket]
        rx = [p["rx_sum"] for p in bucket]
        eng = [p["engagement"] for p in bucket]
        stats["categories"][cat] = {
            "label": RU_LABELS[cat],
            "count": len(bucket),
            "share": round(len(bucket) / len(posts) * 100, 1),
            "avg_views": round(statistics.mean(views)),
            "median_views": round(statistics.median(views)),
            "avg_reactions": round(statistics.mean(rx), 1),
            "avg_engagement_pct": round(statistics.mean(eng) * 100, 2),
            "top_post_id": max(bucket, key=lambda p: p["views"])["id"],
            "top_post_views": max(bucket, key=lambda p: p["views"])["views"],
            "sample_ids": [p["id"] for p in sorted(bucket, key=lambda p: -p["views"])[:5]],
        }

    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    print(f"wrote {OUT.name} ({len(posts)} posts) and {STATS.name}")
    for cat in PRIORITY:
        s = stats["categories"][cat]
        if s.get("count"):
            print(f"  {cat:16s} {s['count']:3d} ({s['share']}%)  "
                  f"avg_views={s.get('avg_views','-')}  avg_rx={s.get('avg_reactions','-')}  "
                  f"eng={s.get('avg_engagement_pct','-')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
