#!/usr/bin/env python3
"""
Keyword-based thematic classification for brazhniki posts.

Reads posts.jsonl, writes posts_cat.jsonl (same posts with "categories" and "primary_category" fields),
and cat_stats.json (per-category counts, avg views, avg reactions, engagement, top posts).

Categories chosen to match brazhniki's own editorial grid: music / cinema / theatre / exhibitions /
parties-clubs / lectures-talks / food-market / outdoor-sports / community-meta / other.

Rule: score each category by (keyword count in text) + (bonus for matching URL/host from a venue list).
Multi-label allowed (categories list); primary = highest score, ties broken by category priority.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSTS = HERE / "posts.jsonl"
OUT = HERE / "posts_cat.jsonl"
STATS = HERE / "cat_stats.json"

# Priority order (used for tie-breaking when scores are equal).
# More specific categories first — "parties" wins over "music" if both match equally.
PRIORITY = [
    "parties_clubs",
    "cinema",
    "theatre",
    "exhibitions",
    "lectures",
    "food_market",
    "outdoor_sports",
    "music",
    "community_meta",
    "other",
]

RU_LABELS = {
    "music":          "музыка (концерты, DJ, live)",
    "cinema":         "кино",
    "theatre":        "театр / перформанс",
    "exhibitions":    "выставки / музеи",
    "parties_clubs":  "вечеринки / клубы",
    "lectures":       "лекции / талки",
    "food_market":    "еда / маркет",
    "outdoor_sports": "улица / спорт",
    "community_meta": "сообщество / мета-посты",
    "other":          "прочее",
}


def _rx(words: list[str], boundary: bool = True) -> re.Pattern:
    # Case-insensitive, with word-ish boundary for latin, loose for cyrillic (Python \b works for cyrillic too in UNICODE).
    joined = "|".join(re.escape(w) for w in words)
    pat = fr"(?i)(?:^|[^A-Za-zА-Яа-яЁё0-9]){joined}(?:[^A-Za-zА-Яа-яЁё0-9]|$)" if boundary else fr"(?i){joined}"
    return re.compile(pat)


KEYWORDS: dict[str, list[str]] = {
    "music": [
        "концерт", "концерты", "live", "лайв", "выступит", "выступление",
        "музыка", "музыкальн", "альбом", "сингл", "трек",
        "техно", "techno", "эмбиент", "ambient", "хаус", "house music",
        "jazz", "джаз", "классическая музыка", "симфони", "оркестр",
        "хор", "сольный", "quartett", "trio", "ensemble", "ансамбль",
        "фортепиано", "гитара", "скрипка", "вокал",
        "fete de la musique", "fête de la musique",
    ],
    "cinema": [
        "кино", "фильм", "фильмы", "показ", "screening",
        "режиссёр", "режиссер",
        "freiluftkino", "open-air cinema", "летний кинотеатр",
        "omeu", "omu", "o(me)u", "o(m)u", "o.m.u.", "o.v.", " ov ", " ov.",
        "babylon", "yorck", "lichtblick", "arsenal", "zeughauskino", "sinema", "sputnik kino",
        "кинопоказ", "documentary", "документальн",
    ],
    "theatre": [
        "театр", "спектакль", "перформанс", "performance",
        "schaubühne", "schaubuhne", "volksbühne", "volksbuhne", "berliner ensemble",
        "deutsches theater", "hau", "sophiensaele", "ballhaus",
        "танцспектакл", "танцевальн", "contemporary dance", "танц ",
    ],
    "exhibitions": [
        "выставк", "exhibition", "ausstellung",
        "музей", "museum",
        "hamburger bahnhof", "humboldt", "pergamon",
        "neue nationalgalerie", "kw ", "n.b.k", "gropius bau", "gropiusbau",
        "berlinische galerie", "c/o berlin", "haus der kulturen",
        "галерея", "gallery",
    ],
    "parties_clubs": [
        "вечеринк", "party", "rave", "рейв",
        "клуб ", "клубе ", "клуба ", "клубы",
        "berghain", "about blank", "aboutblank", ":// about",
        "sisyphos", "renate", "ohm", "tresor", "kater blau", "katerblau",
        "ritter butzke", "ritterbutzke", "watergate", "kitkat", "kit kat",
        "panda", "so36", "gretchen", "privatclub",
        "closing", "opening", "резиденты", "lineup", "line-up", "line up",
        "танцпол", "techno-party", "техно-вечеринк", "техно вечеринк",
        "ночнаяж", "rave",
    ],
    "lectures": [
        "лекци", "lecture", "talk", "воркшоп", "workshop",
        "дискуссия", "discussion", "panel", "панель", "семинар",
        "презентаци", "презентация книги", "book launch", "книжная презентация",
        "конференц", "conference",
        "воркшоп", "мастер-класс", "мастеркласс",
    ],
    "food_market": [
        "ужин", "обед", "брунч", "brunch",
        "маркет", "market", "ярмарк", "fair",
        "фудмаркет", "food market", "street food", "еда ",
        "ресторан", "пекарн", "бар ", "cocktail", "коктейл", "дегустаци", "tasting",
        "flohmarkt", "блошин",
    ],
    "outdoor_sports": [
        "прогулк", "walk ", "hike", "хайк", "поход",
        "велосипед", "cycling", "bike ride",
        "забег", "run ", "running", "марафон",
        "йога ", "yoga ",
        "озеро", "see ", "schwimmen", "купан", "swim",
        "ботанический сад", "botanischer",
        "парк ", "park ",
    ],
    "community_meta": [
        "наш канал", "подписыв", "репост", "спасибо что читаете",
        "обратная связь", "фидбек", "feedback",
        "реклам", "advertising", "sponsored", "@eventswerbungbot",
        "просим поддержать", "donate", "донат",
        "мы — ", "мы -", "о канале",
    ],
}

VENUE_HOST_HINTS: dict[str, list[str]] = {
    "cinema": [
        "freiluftkino", "babylonberlin.eu", "yorck.de", "lichtblick-kino.org",
        "arsenal-berlin.de", "zeughauskino", "sputnik-kino", "ilkinos",
    ],
    "parties_clubs": [
        "berghain.berlin", "ra.co", "dice.fm", "resident-advisor",
        "so36.com", "gretchen-club.de", "privatclub-berlin.de",
        "ohmberlin", "renate.cc", "kater", "watergate.de", "kitkat",
        "panda-platforma.berlin",
    ],
    "exhibitions": [
        "smb.museum", "humboldtforum.org", "berlinischegalerie",
        "neue-nationalgalerie", "gropiusbau", "kw-berlin.de",
        "co-berlin", "hkw.de", "nbk.org", "hamburger-bahnhof",
    ],
    "theatre": [
        "schaubuehne", "volksbuehne", "berliner-ensemble",
        "deutschestheater", "hebbel-am-ufer", "sophiensaele",
    ],
    "music": [
        "konzerthaus.de", "berliner-philharmoniker",
        "silent-green.net", "fetedelamusique.de",
    ],
    "food_market": [
        "markthalleneun", "flohmarkt",
    ],
    "lectures": [
        "berlinerfestspiele.de",  # often lectures/talks mix with theatre; keep weak signal
    ],
}


def classify(text: str, text_html: str) -> tuple[dict[str, int], str]:
    """Return (scores_per_category, primary_category)."""
    scores: dict[str, int] = defaultdict(int)
    full = f"{text}\n{text_html}"

    for cat, words in KEYWORDS.items():
        rx = _rx(words)
        hits = rx.findall(full)
        if hits:
            scores[cat] += len(hits)

    # URL/host bonus
    for cat, hosts in VENUE_HOST_HINTS.items():
        for host in hosts:
            if host in text_html.lower() or host in text.lower():
                scores[cat] += 2  # URL hit is strong signal

    if not scores:
        return {}, "other"

    max_score = max(scores.values())
    best = [c for c in PRIORITY if scores.get(c) == max_score]
    return dict(scores), best[0]


def main() -> int:
    posts = [json.loads(l) for l in POSTS.open()]
    posts = [p for p in posts if not p.get("is_service") and p.get("views", 0) > 0]

    for p in posts:
        scores, primary = classify(p.get("text", ""), p.get("text_html", ""))
        p["cat_scores"] = scores
        p["primary_category"] = primary
        p["categories"] = sorted(scores.keys(), key=lambda c: -scores[c])
        p["rx_sum"] = sum(p["reactions"].values())
        p["engagement"] = (p["rx_sum"] / p["views"]) if p["views"] else 0

    with OUT.open("w") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # per-category aggregates
    stats: dict = {"total_posts": len(posts), "categories": {}}
    for cat in list(KEYWORDS.keys()) + ["other"]:
        bucket = [p for p in posts if p["primary_category"] == cat]
        if not bucket:
            stats["categories"][cat] = {"label": RU_LABELS[cat], "count": 0}
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
    for cat, s in stats["categories"].items():
        if s.get("count"):
            print(f"  {cat:16s} {s['count']:3d} ({s['share']}%)  "
                  f"avg_views={s['avg_views']}  avg_rx={s['avg_reactions']}  "
                  f"eng={s['avg_engagement_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
