#!/usr/bin/env python3
"""
Analyze posts.jsonl → write report.md + stats.json + tops.md.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSTS = HERE / "posts.jsonl"
CHANNEL = HERE / "channel.json"
REPORT = HERE / "report.md"
TOPS = HERE / "tops.md"
STATS = HERE / "stats.json"

RU_DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
RU_MONTH = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def load() -> tuple[list[dict], dict]:
    posts = [json.loads(l) for l in POSTS.open()]
    posts = [p for p in posts if not p.get("is_service") and p.get("views", 0) > 0]
    posts.sort(key=lambda p: p["id"])
    meta = json.loads(CHANNEL.read_text()) if CHANNEL.exists() else {}
    return posts, meta


def pct(xs: list[int], q: float) -> float:
    if not xs:
        return 0
    k = (len(xs) - 1) * q
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    xs = sorted(xs)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def fmt_int(n: int | float) -> str:
    return f"{int(n):,}".replace(",", " ")


def dt_local(iso: str) -> datetime:
    """Return Berlin-ish local time (UTC+1/+2, approximate CEST = +2)."""
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    # Berlin is UTC+1 (winter) / UTC+2 (summer). Approx: +2 Mar-Oct, +1 Nov-Feb.
    offset = 2 if 3 <= d.month <= 10 else 1
    return d.astimezone(timezone.utc).replace(tzinfo=None).replace(hour=(d.hour + offset) % 24)


URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+", re.I)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)
MENTION_RE = re.compile(r"(?<![\w@/])@([A-Za-z0-9_]{3,32})")
HASHTAG_RE = re.compile(r"(?<!\w)#([^\s#.,;:!?()\[\]{}'\"«»]+)")
TME_URL_RE = re.compile(r"https?://t\.me/([A-Za-z0-9_]+)(?:/\d+)?", re.I)


def main() -> int:
    posts, meta = load()
    N = len(posts)
    first = posts[0]
    last = posts[-1]
    days_covered = (
        datetime.fromisoformat(last["date"].replace("Z", "+00:00"))
        - datetime.fromisoformat(first["date"].replace("Z", "+00:00"))
    ).days + 1

    views = [p["views"] for p in posts]
    total_reactions = sum(sum(p["reactions"].values()) for p in posts)
    rx_counter: Counter[str] = Counter()
    for p in posts:
        for e, c in p["reactions"].items():
            rx_counter[e] += c

    media = Counter(p["media_type"] or "text_only" for p in posts)
    edited = sum(1 for p in posts if p.get("edited"))
    forwarded = sum(1 for p in posts if p.get("forwarded_from"))
    replies = sum(1 for p in posts if p.get("reply_to_id"))

    # engagement
    for p in posts:
        p["rx_sum"] = sum(p["reactions"].values())
        p["engagement"] = p["rx_sum"] / p["views"] if p["views"] else 0

    # time patterns (Berlin local)
    by_dow: Counter[int] = Counter()
    by_hour: Counter[int] = Counter()
    by_month: Counter[str] = Counter()
    views_by_dow: dict[int, list[int]] = defaultdict(list)
    views_by_hour: dict[int, list[int]] = defaultdict(list)
    for p in posts:
        d = dt_local(p["date"])
        by_dow[d.weekday()] += 1
        by_hour[d.hour] += 1
        by_month[f"{d.year}-{d.month:02d}"] += 1
        views_by_dow[d.weekday()].append(p["views"])
        views_by_hour[d.hour].append(p["views"])

    # posting cadence (gaps in hours between consecutive non-service posts)
    gaps_hours = []
    for a, b in zip(posts, posts[1:]):
        da = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
        db = datetime.fromisoformat(b["date"].replace("Z", "+00:00"))
        gaps_hours.append((db - da).total_seconds() / 3600)

    # growth proxy — views by month
    monthly_views: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        d = dt_local(p["date"])
        monthly_views[f"{d.year}-{d.month:02d}"].append(p["views"])

    # content signals — URLs/mentions mostly come from <a href> in text_html
    url_counter: Counter[str] = Counter()
    tme_counter: Counter[str] = Counter()
    mention_counter: Counter[str] = Counter()
    hashtag_counter: Counter[str] = Counter()

    def _norm_host(url: str) -> str | None:
        m = re.match(r"https?://([^/]+)/?", url, re.I)
        if not m:
            return None
        host = m.group(1).lower()
        return re.sub(r"^www\.", "", host)

    for p in posts:
        th = p.get("text_html", "") or ""
        urls = set()
        # 1. explicit <a href=...> links
        for href in HREF_RE.findall(th):
            urls.add(href)
            m = TME_URL_RE.match(href)
            if m:
                tme_counter["@" + m.group(1)] += 1
        # 2. plain-text URLs in rendered text
        for u in URL_RE.findall(p["text"]):
            urls.add(u)
            m = TME_URL_RE.match(u)
            if m:
                tme_counter["@" + m.group(1)] += 1
        for u in urls:
            host = _norm_host(u)
            if host:
                url_counter[host] += 1
        # @mentions in rendered text
        for m in MENTION_RE.findall(p["text"]):
            mention_counter["@" + m] += 1
        for h in HASHTAG_RE.findall(p["text"]):
            if re.fullmatch(r"\d+", h):
                continue  # skip "#5" etc. (likely list indices)
            hashtag_counter["#" + h.lower()] += 1

    # Merge t.me/<name> links into mentions so @woberlin via href is counted
    for u, c in tme_counter.items():
        mention_counter[u] += c

    # tops
    top_views = sorted(posts, key=lambda p: p["views"], reverse=True)[:25]
    top_reactions = sorted(posts, key=lambda p: p["rx_sum"], reverse=True)[:25]
    # engagement — only posts with ≥500 views to avoid noise
    eng_candidates = [p for p in posts if p["views"] >= 500]
    top_engagement = sorted(eng_candidates, key=lambda p: p["engagement"], reverse=True)[:25]
    low_views = sorted(posts, key=lambda p: p["views"])[:15]

    # ---- write stats.json ----
    stats = {
        "channel": meta,
        "posts_total": N,
        "id_range": [posts[0]["id"], posts[-1]["id"]],
        "deleted_or_service": posts[-1]["id"] - posts[0]["id"] + 1 - len(posts),
        "date_range": [first["date"], last["date"]],
        "days_covered": days_covered,
        "posts_per_day_avg": round(N / max(days_covered, 1), 2),
        "views": {
            "total": sum(views),
            "min": min(views),
            "p25": int(pct(views, 0.25)),
            "median": int(pct(views, 0.5)),
            "p75": int(pct(views, 0.75)),
            "p90": int(pct(views, 0.9)),
            "p95": int(pct(views, 0.95)),
            "max": max(views),
            "avg": round(statistics.mean(views)),
        },
        "reactions": {
            "total": total_reactions,
            "avg_per_post": round(total_reactions / N, 1),
            "posts_with_any": sum(1 for p in posts if p["rx_sum"]),
            "top_emoji": rx_counter.most_common(20),
        },
        "media": dict(media),
        "edited_posts": edited,
        "forwarded_posts": forwarded,
        "reply_posts": replies,
        "posts_by_dow": {RU_DOW[i]: by_dow.get(i, 0) for i in range(7)},
        "posts_by_hour": {str(h): by_hour.get(h, 0) for h in range(24)},
        "posts_by_month": dict(sorted(by_month.items())),
        "avg_views_by_dow": {RU_DOW[i]: round(statistics.mean(views_by_dow[i])) if views_by_dow[i] else 0 for i in range(7)},
        "avg_views_by_hour": {str(h): round(statistics.mean(views_by_hour[h])) if views_by_hour[h] else 0 for h in range(24)},
        "avg_views_by_month": {m: round(statistics.mean(vs)) for m, vs in sorted(monthly_views.items())},
        "gap_hours": {
            "median": round(statistics.median(gaps_hours), 1) if gaps_hours else 0,
            "mean": round(statistics.mean(gaps_hours), 1) if gaps_hours else 0,
            "max": round(max(gaps_hours), 1) if gaps_hours else 0,
        },
        "top_domains": url_counter.most_common(30),
        "top_mentions": mention_counter.most_common(30),
        "top_hashtags": hashtag_counter.most_common(30),
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    # ---- write report.md ----
    def bar(frac: float, width: int = 30) -> str:
        n = int(round(frac * width))
        return "█" * n + "·" * (width - n)

    lines: list[str] = []
    lines.append(f"# Статистика канала @butterflies_and_berliners")
    lines.append("")
    lines.append(f"Сбор: {datetime.now().strftime('%Y-%m-%d %H:%M')} · источник: публичный превью `t.me/s/...`")
    lines.append("")
    lines.append(f"## О канале")
    lines.append("")
    lines.append(f"- **Название:** {meta.get('title','—')}")
    lines.append(f"- **Описание:** {meta.get('description','—')}")
    lines.append(f"- **Подписчики:** {meta.get('subscribers','?')}")
    lines.append(f"- **Фото:** {meta.get('photos','?')} · **видео:** {meta.get('videos','?')} · **ссылки:** {meta.get('links','?')}")
    lines.append(f"- **Диапазон постов:** id {posts[0]['id']}..{posts[-1]['id']} ({posts[-1]['id']-posts[0]['id']+1} слотов), из них {N} существует, {stats['deleted_or_service']} удалено/сервисных")
    lines.append(f"- **Период:** {first['date'][:10]} .. {last['date'][:10]} ({days_covered} дней)")
    lines.append(f"- **Темп:** {stats['posts_per_day_avg']} постов/день, медианный интервал {stats['gap_hours']['median']} ч")
    lines.append("")
    lines.append(f"## Просмотры (на дату сбора)")
    lines.append("")
    v = stats["views"]
    lines.append(f"- Всего накоплено: **{fmt_int(v['total'])}** views на {N} постах")
    lines.append(f"- Среднее: **{fmt_int(v['avg'])}** / пост · медиана: **{fmt_int(v['median'])}**")
    lines.append(f"- Квантили: p25={fmt_int(v['p25'])} · p75={fmt_int(v['p75'])} · p90={fmt_int(v['p90'])} · p95={fmt_int(v['p95'])}")
    lines.append(f"- Min={fmt_int(v['min'])}, Max=**{fmt_int(v['max'])}**")
    lines.append("")
    lines.append(f"## Реакции")
    lines.append("")
    r = stats["reactions"]
    lines.append(f"- Всего реакций: **{fmt_int(r['total'])}** на {r['posts_with_any']} постах (из {N}, {r['posts_with_any']*100//N}%)")
    lines.append(f"- Среднее: {r['avg_per_post']} реакций/пост")
    lines.append(f"- Топ эмодзи:")
    lines.append("")
    lines.append("| эмодзи | кол-во |")
    lines.append("|---|---:|")
    for e, c in r["top_emoji"]:
        lines.append(f"| {e} | {fmt_int(c)} |")
    lines.append("")
    lines.append(f"## Медиа")
    lines.append("")
    for k, c in sorted(media.items(), key=lambda x: -x[1]):
        lines.append(f"- **{k}**: {c} ({c*100//N}%)")
    lines.append(f"- Редактированные: {edited} · форварды: {forwarded} · реплаи: {replies}")
    lines.append("")
    lines.append(f"## Когда постят (локальное Берлинское время)")
    lines.append("")
    lines.append(f"### По дням недели")
    lines.append("")
    max_dow = max(by_dow.values())
    for i in range(7):
        c = by_dow.get(i, 0)
        avg_v = round(statistics.mean(views_by_dow[i])) if views_by_dow[i] else 0
        lines.append(f"- **{RU_DOW[i]}**  `{bar(c/max_dow)}` {c:3d} постов · avg views {fmt_int(avg_v)}")
    lines.append("")
    lines.append(f"### По часам")
    lines.append("")
    max_h = max(by_hour.values())
    for h in range(24):
        c = by_hour.get(h, 0)
        if c == 0:
            continue
        avg_v = round(statistics.mean(views_by_hour[h])) if views_by_hour[h] else 0
        lines.append(f"- **{h:02d}:00**  `{bar(c/max_h)}` {c:3d} · avg views {fmt_int(avg_v)}")
    lines.append("")
    lines.append(f"## Динамика по месяцам")
    lines.append("")
    lines.append("| месяц | постов | avg views |")
    lines.append("|---|---:|---:|")
    for m, c in sorted(by_month.items()):
        avg_v = round(statistics.mean(monthly_views[m])) if monthly_views.get(m) else 0
        lines.append(f"| {m} | {c} | {fmt_int(avg_v)} |")
    lines.append("")
    lines.append(f"## Темп публикаций")
    lines.append("")
    g = stats["gap_hours"]
    lines.append(f"- Медианный разрыв между постами: **{g['median']} ч**")
    lines.append(f"- Средний: {g['mean']} ч")
    lines.append(f"- Самый длинный: {g['max']} ч")
    lines.append("")
    lines.append(f"## Упоминаемые домены (top 30)")
    lines.append("")
    for d, c in url_counter.most_common(30):
        lines.append(f"- {d} — {c}")
    lines.append("")
    lines.append(f"## Упоминаемые @ (top 30)")
    lines.append("")
    for u, c in mention_counter.most_common(30):
        lines.append(f"- {u} — {c}")
    lines.append("")
    lines.append(f"## Хэштеги (top 30)")
    lines.append("")
    if hashtag_counter:
        for h, c in hashtag_counter.most_common(30):
            lines.append(f"- {h} — {c}")
    else:
        lines.append("_нет_")

    REPORT.write_text("\n".join(lines))

    # ---- write tops.md ----
    def post_link(p: dict) -> str:
        return f"https://t.me/butterflies_and_berliners/{p['id']}"

    def row(p: dict) -> str:
        preview = p["text"][:150].replace("\n", " ⏎ ")
        return (
            f"- [{p['id']}]({post_link(p)}) · {p['date'][:10]} · "
            f"views **{fmt_int(p['views'])}** · rx {fmt_int(p['rx_sum'])} · "
            f"eng {p['engagement']*100:.1f}% · {p['media_type'] or 'text'}  \n"
            f"  _{preview}_"
        )

    lines = []
    lines.append("# Top-посты")
    lines.append("")
    lines.append("## Top-25 по просмотрам")
    lines.append("")
    for p in top_views:
        lines.append(row(p))
    lines.append("")
    lines.append("## Top-25 по сумме реакций")
    lines.append("")
    for p in top_reactions:
        lines.append(row(p))
    lines.append("")
    lines.append("## Top-25 по engagement (reactions/views, посты ≥500 views)")
    lines.append("")
    for p in top_engagement:
        lines.append(row(p))
    lines.append("")
    lines.append("## Низ-15 по просмотрам")
    lines.append("")
    for p in low_views:
        lines.append(row(p))

    TOPS.write_text("\n".join(lines))

    print(f"wrote: {REPORT.name}, {TOPS.name}, {STATS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
