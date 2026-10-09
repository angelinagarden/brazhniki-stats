#!/usr/bin/env python3
"""
Parse weekly digest posts ("События недели: ...") into per-topic event counts.

Digests have a clean structure: short section headers (Выставки / Концерты / ...)
followed by event lines. For each digest, count events per topic category and
save to digests_topics.json, keyed by post id.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSTS = HERE / "posts_cat.jsonl"
OUT = HERE / "digests_topics.json"

HEADER_TO_CAT: dict[str, str] = {
    # exhibitions / museums
    "выставки": "exhibitions",
    "выставка": "exhibitions",
    "музеи": "exhibitions",
    "галереи": "exhibitions",
    "art": "exhibitions",
    "exhibitions": "exhibitions",
    # markets / flea
    "маркеты": "food_market",
    "маркет": "food_market",
    "фудмаркет": "food_market",
    "flohmarkt": "food_market",
    "еда": "food_market",
    "food": "food_market",
    # clubs / parties
    "клубы": "club_party",
    "клуб": "club_party",
    "clubbing": "club_party",
    "вечеринки": "club_party",
    "вечеринка": "club_party",
    "parties": "club_party",
    "техно": "club_party",
    "рейв": "club_party",
    # concerts (general)
    "концерты": "music_concert",
    "концерт": "music_concert",
    "музыка": "music_concert",
    "live": "music_concert",
    "music": "music_concert",
    # classical / opera / jazz
    "классика": "music_classical",
    "опера": "music_classical",
    "джаз": "music_classical",
    "classical": "music_classical",
    "jazz": "music_classical",
    "оркестр": "music_classical",
    # cinema
    "кино": "cinema",
    "фильмы": "cinema",
    "фильм": "cinema",
    "кинопоказы": "cinema",
    "cinema": "cinema",
    "films": "cinema",
    "film": "cinema",
    # theatre / dance / performance
    "театр": "theatre_dance",
    "спектакли": "theatre_dance",
    "перформанс": "theatre_dance",
    "танцы": "theatre_dance",
    "performance": "theatre_dance",
    "theater": "theatre_dance",
    "theatre": "theatre_dance",
    # lectures / talks
    "лекции": "lectures_talks",
    "лекция": "lectures_talks",
    "talks": "lectures_talks",
    "talk": "lectures_talks",
    "дискуссии": "lectures_talks",
    "воркшоп": "lectures_talks",
    "workshop": "lectures_talks",
    # outdoor / sports
    "прогулки": "outdoor_sports",
    "прогулка": "outdoor_sports",
    "спорт": "outdoor_sports",
    "walks": "outdoor_sports",
    "sports": "outdoor_sports",
    "outdoor": "outdoor_sports",
    "хайки": "outdoor_sports",
    "hikes": "outdoor_sports",
    "йога": "outdoor_sports",
}


HEADER_WORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё &/-]{3,40}$")  # short line, letters + separators only

DOW_RE = re.compile(r"^(понедельник|вторник|среда|четверг|пятниц[ау]|суббот[ау]|воскресень[ея]|пн|вт|ср|чт|пт|сб|вс)[,.\s]", re.I)

# Event-text classifiers (lower-priority than section headers).
# Rough patterns applied to the full event line.
EVENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("music_classical", re.compile(r"\b(органн|оркестр|симфон|класси\w*|опер[аы]\b|джаз|jazz|chamber|philharmoni|konzerthaus|liedabend|струнн)", re.I)),
    ("cinema",          re.compile(r"\b(freiluftkino|кино|фильм|screening|babylon|yorck|lichtblick|arsenal\b|zeughauskino|sputnik.?kino|omeu|omu|cinemateca|мультфильм)", re.I)),
    ("club_party",      re.compile(r"\b(berghain|about.?blank|sisyphos|renate|ohm|tresor|kater.?blau|ritter.?butzke|watergate|kitkat|panda|so36|gretchen|privatclub|клуб|клубн|вечеринк|rave|рейв|club.?night|klubnacht|closing|opening|dj.?set|techno|танцпол|afters?party)", re.I)),
    ("theatre_dance",   re.compile(r"\b(театр|спектакль|перформанс|performance|schaubühne|schaubuhne|volksb[uü]hne|berliner ensemble|deutsches theater|hau[1-4]?\b|sophiensaele|ballhaus|танцспектакл|contemporary dance|танцевальн)", re.I)),
    ("exhibitions",     re.compile(r"\b(выставк|exhibition|ausstellung|музе[йя]|museum|гропиус|humboldt|pergamon|hamburger bahnhof|neue nationalgalerie|kw[\s-]|gropius ?bau|berlinische galerie|c/o berlin|haus der kulturen|hkw|галере|gallery|vernissage|er[öo]ffnung)", re.I)),
    ("lectures_talks",  re.compile(r"\b(лекци|lecture|talk\b|дискусси|discussion|панель|panel|book launch|презентаци|voркшоп|workshop|conference|мастер.?класс|стендап|comedy)", re.I)),
    ("food_market",     re.compile(r"\b(flohmarkt|блошин|рынок|market|markt\b|фудмаркет|food market|street food|дегустаци|tasting|ресторан|брунч|brunch|ярмарк|fair\b|markthalle)", re.I)),
    ("outdoor_sports",  re.compile(r"\b(прогулк|walk\b|hike|хайк|поход|велосипед|cycling|bike|забег|run\b|running|марафон|йога|yoga|озеро|see\b|schwimmen|купан|swim|ботаническ|парк|пикник|picnic)", re.I)),
    ("music_concert",   re.compile(r"\b(концерт|live\b|выступит|выступлен|сольн|band|группа|солист|k.?pop|рок|rock|indie|metal|pop\b|панк|punk|folk|ambient|электроник|experimental)", re.I)),
]


def normalize_header(line: str) -> str | None:
    """Match topic section headers (old digest format)."""
    line = line.strip().rstrip(":").strip()
    if not line:
        return None
    if not HEADER_WORD_RE.match(line):
        return None
    low = line.lower().replace("ё", "е")
    if low in HEADER_TO_CAT:
        return HEADER_TO_CAT[low]
    first = low.split()[0] if low.split() else ""
    if first in HEADER_TO_CAT:
        return HEADER_TO_CAT[first]
    return None


def is_dow_header(line: str) -> bool:
    """Day-of-week section header (new digest format)."""
    return bool(DOW_RE.match(line.strip()))


def looks_like_event_line(line: str) -> bool:
    s = line.strip()
    if len(s) < 15:
        return False
    # Starts with marker ("/ ", "— ", "* ", "- ", bullet)
    if re.match(r"^[/—*•\-]\s|^/\s*", s):
        return True
    # Or has time/paren/digit (old format)
    return bool(re.search(r"[(\d—–:]", s))


def classify_event_text(line: str) -> str | None:
    """Guess category from a single event line's content."""
    for cat, rx in EVENT_PATTERNS:
        if rx.search(line):
            return cat
    return None


def parse_digest(text: str) -> Counter:
    """Return Counter of category -> event count for one digest."""
    counts: Counter = Counter()
    current_header_cat: str | None = None  # old-format section header
    in_dow_mode = False                     # new-format: classify per event text
    lines = text.split("\n")
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("события недели"):
            continue
        if is_dow_header(line):
            in_dow_mode = True
            current_header_cat = None
            continue
        header_cat = normalize_header(line)
        if header_cat:
            current_header_cat = header_cat
            in_dow_mode = False
            continue
        if looks_like_event_line(line):
            # New format (dow sections): classify by event text
            if in_dow_mode:
                cat = classify_event_text(line)
                if cat:
                    counts[cat] += 1
                else:
                    counts["other"] += 1
            elif current_header_cat:
                counts[current_header_cat] += 1
    return counts


def main() -> int:
    posts = [json.loads(l) for l in POSTS.open()]
    digests = [p for p in posts if p["primary_category"] == "digest"]
    print(f"found {len(digests)} digests")

    result: dict[str, dict] = {}
    totals: Counter = Counter()
    for d in digests:
        c = parse_digest(d["text"])
        result[str(d["id"])] = {
            "id": d["id"],
            "date": d["date"],
            "total_events": sum(c.values()),
            "by_category": dict(c),
        }
        for k, v in c.items():
            totals[k] += v

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"wrote {OUT.name}")
    print("totals across all digests:")
    for cat, n in totals.most_common():
        print(f"  {cat:20s} {n}")

    # sample
    sample_id = next(iter(result))
    print(f"\nsample digest id={sample_id}: {result[sample_id]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
