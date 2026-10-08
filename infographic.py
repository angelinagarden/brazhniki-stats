#!/usr/bin/env python3
"""
Render infographics as PNG from posts_cat.jsonl + stats.json + cat_stats.json.

Outputs to figs/:
  00_dashboard.png            — single-page composite (all panels)
  01_categories_pie.png
  02_categories_bars.png
  03_views_by_dow_hour.png
  04_timeline_stacked.png
  05_top_emoji.png
  06_top_domains.png
  07_views_distribution.png
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

HERE = Path(__file__).resolve().parent
FIGS = HERE / "figs"
FIGS.mkdir(exist_ok=True)

POSTS = HERE / "posts_cat.jsonl"
CAT_STATS = HERE / "cat_stats.json"
STATS = HERE / "stats.json"
CHANNEL = HERE / "channel.json"

RU_DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# Palette (reasonably distinct, print-friendly)
CAT_COLORS = {
    "music_concert":   "#e74c3c",
    "music_classical": "#6c3483",
    "club_party":      "#1abc9c",
    "cinema":          "#f39c12",
    "theatre_dance":   "#9b59b6",
    "exhibitions":     "#3498db",
    "lectures_talks":  "#95a5a6",
    "food_market":     "#e67e22",
    "outdoor_sports":  "#27ae60",
    "digest":          "#f1c40f",
    "community_meta":  "#7f8c8d",
    "other":           "#bdc3c7",
}
CAT_ORDER = ["music_concert", "cinema", "exhibitions", "club_party", "theatre_dance",
             "digest", "outdoor_sports", "lectures_talks", "food_market",
             "music_classical", "community_meta", "other"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def load():
    posts = [json.loads(l) for l in POSTS.open()]
    cat = json.loads(CAT_STATS.read_text())
    stats = json.loads(STATS.read_text())
    channel = json.loads(CHANNEL.read_text()) if CHANNEL.exists() else {}
    return posts, cat, stats, channel


def dt_local(iso: str) -> datetime:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    offset = 2 if 3 <= d.month <= 10 else 1
    return d.astimezone(timezone.utc).replace(tzinfo=None).replace(hour=(d.hour + offset) % 24)


# ---------- individual panels ----------

def _cat_label(cat: str, c: dict) -> str:
    return c["categories"][cat]["label"]


def panel_pie(ax, posts, cat_stats):
    present = [c for c in CAT_ORDER if cat_stats["categories"][c]["count"] > 0]
    sizes = [cat_stats["categories"][c]["count"] for c in present]
    labels = [f"{_cat_label(c, cat_stats)}\n{sizes[i]} ({cat_stats['categories'][c]['share']}%)"
              for i, c in enumerate(present)]
    colors = [CAT_COLORS[c] for c in present]
    wedges, _ = ax.pie(sizes, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"linewidth": 1.5, "edgecolor": "white"})
    ax.set_title("Распределение постов по тематике")
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5),
              fontsize=9, frameon=False)


def panel_cat_bars(ax, cat_stats):
    present = [c for c in CAT_ORDER if cat_stats["categories"][c]["count"] > 0]
    avg_views = [cat_stats["categories"][c]["avg_views"] for c in present]
    labels = [_cat_label(c, cat_stats) for c in present]
    colors = [CAT_COLORS[c] for c in present]
    order = np.argsort(avg_views)[::-1]
    y = np.arange(len(present))
    ax.barh(y, [avg_views[i] for i in order], color=[colors[i] for i in order])
    ax.set_yticks(y)
    ax.set_yticklabels([labels[i] for i in order])
    ax.invert_yaxis()
    ax.set_xlabel("avg views")
    ax.set_title("Средние просмотры по тематике")
    for i, v in enumerate([avg_views[i] for i in order]):
        ax.text(v + max(avg_views) * 0.01, i, f"{v:,}".replace(",", " "),
                va="center", fontsize=9)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x/1000)}K" if x >= 1000 else int(x)))


def panel_eng_bars(ax, cat_stats):
    present = [c for c in CAT_ORDER if cat_stats["categories"][c]["count"] > 0]
    eng = [cat_stats["categories"][c]["avg_engagement_pct"] for c in present]
    labels = [_cat_label(c, cat_stats) for c in present]
    colors = [CAT_COLORS[c] for c in present]
    order = np.argsort(eng)[::-1]
    y = np.arange(len(present))
    ax.barh(y, [eng[i] for i in order], color=[colors[i] for i in order])
    ax.set_yticks(y)
    ax.set_yticklabels([labels[i] for i in order])
    ax.invert_yaxis()
    ax.set_xlabel("engagement, %  (reactions / views)")
    ax.set_title("Engagement rate по тематике")
    for i, v in enumerate([eng[i] for i in order]):
        ax.text(v + max(eng) * 0.01, i, f"{v:.2f}%", va="center", fontsize=9)


def panel_dow_hour(ax, posts):
    heat = np.zeros((7, 24))
    for p in posts:
        d = dt_local(p["date"])
        heat[d.weekday(), d.hour] += 1
    im = ax.imshow(heat, aspect="auto", cmap="YlOrRd", origin="upper")
    ax.set_yticks(range(7))
    ax.set_yticklabels(RU_DOW)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("час (Berlin)")
    ax.set_title("Когда постят (кол-во постов, час × день недели)")
    for i in range(7):
        for j in range(24):
            if heat[i, j] > 0:
                ax.text(j, i, int(heat[i, j]), ha="center", va="center",
                        fontsize=7, color="black" if heat[i, j] < heat.max() * 0.6 else "white")
    plt.colorbar(im, ax=ax, label="постов", shrink=0.8)


def panel_timeline(ax, posts):
    """Stacked weekly posts per category."""
    weeks: dict[str, Counter] = defaultdict(Counter)
    for p in posts:
        d = dt_local(p["date"])
        # ISO week start Monday
        y, w, _ = d.isocalendar()
        key = f"{y}-W{w:02d}"
        weeks[key][p["primary_category"]] += 1
    week_keys = sorted(weeks.keys())
    present = [c for c in CAT_ORDER if sum(weeks[w][c] for w in week_keys) > 0]
    series = {c: [weeks[w][c] for w in week_keys] for c in present}
    labels = [cat_label_short(c) for c in present]
    colors = [CAT_COLORS[c] for c in present]
    bottom = np.zeros(len(week_keys))
    for c, lbl, col in zip(present, labels, colors):
        vals = np.array(series[c])
        ax.bar(range(len(week_keys)), vals, bottom=bottom, label=lbl, color=col, width=1.0)
        bottom += vals
    tick_every = max(1, len(week_keys) // 12)
    ax.set_xticks(range(0, len(week_keys), tick_every))
    ax.set_xticklabels([week_keys[i] for i in range(0, len(week_keys), tick_every)],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("постов / неделю")
    ax.set_title("Постинг по неделям, стек по тематике")
    ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)


def panel_top_emoji(ax, stats):
    emoji = stats["reactions"]["top_emoji"][:15]
    labels = [e for e, _ in emoji]
    vals = [c for _, c in emoji]
    y = np.arange(len(labels))
    ax.barh(y, vals, color="#e74c3c")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=14)
    ax.invert_yaxis()
    ax.set_xlabel("реакций")
    ax.set_title(f"Топ-реакций (всего {stats['reactions']['total']:,})".replace(",", " "))
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, f"{v:,}".replace(",", " "),
                va="center", fontsize=9)


def panel_top_domains(ax, stats, limit: int = 20):
    doms = stats["top_domains"][:limit]
    doms = [(d, c) for d, c in doms if d not in {"t.me"}]  # drop in-telegram cross-links
    doms = doms[:limit]
    labels = [d for d, _ in doms]
    vals = [c for _, c in doms]
    y = np.arange(len(labels))
    ax.barh(y, vals, color="#3498db")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("ссылок")
    ax.set_title(f"Топ-{limit} внешних доменов (без t.me)")
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, str(v), va="center", fontsize=9)


def panel_views_dist(ax, posts):
    views = [p["views"] for p in posts]
    ax.hist(views, bins=40, color="#f39c12", edgecolor="white")
    ax.axvline(np.median(views), color="black", linestyle="--", lw=1,
               label=f"медиана {int(np.median(views)):,}".replace(",", " "))
    ax.axvline(np.mean(views), color="red", linestyle="--", lw=1,
               label=f"среднее {int(np.mean(views)):,}".replace(",", " "))
    ax.set_xlabel("views")
    ax.set_ylabel("постов")
    ax.set_title("Распределение просмотров по постам")
    ax.legend(frameon=False)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x/1000)}K" if x >= 1000 else int(x)))


def cat_label_short(c: str) -> str:
    return {
        "music_concert":   "концерты",
        "music_classical": "классика",
        "club_party":      "клубы",
        "cinema":          "кино",
        "theatre_dance":   "театр",
        "exhibitions":     "выставки",
        "lectures_talks":  "лекции",
        "food_market":     "еда",
        "outdoor_sports":  "улица",
        "digest":          "дайджест",
        "community_meta":  "мета",
        "other":           "прочее",
    }.get(c, c)


# ---------- dashboard ----------

def dashboard(posts, cat_stats, stats, channel):
    fig = plt.figure(figsize=(18, 24))
    gs = fig.add_gridspec(5, 2, height_ratios=[0.8, 2.2, 2.2, 2.2, 2.2], hspace=0.45, wspace=0.3)

    # Header
    ax_h = fig.add_subplot(gs[0, :])
    ax_h.axis("off")
    title = f"@butterflies_and_berliners — срез на {datetime.now().strftime('%Y-%m-%d')}"
    subtitle = (f"{channel.get('subscribers','?')} подписчиков  ·  {stats['posts_total']} постов "
                f"({stats['date_range'][0][:10]}..{stats['date_range'][1][:10]}, {stats['days_covered']} дней)  "
                f"·  темп: {stats['posts_per_day_avg']} постов/день  ·  "
                f"медиана views {stats['views']['median']:,}  ·  всего реакций: {stats['reactions']['total']:,}"
                ).replace(",", " ")
    ax_h.text(0.5, 0.65, title, ha="center", va="center", fontsize=22, fontweight="bold")
    ax_h.text(0.5, 0.15, subtitle, ha="center", va="center", fontsize=11, color="#555")

    panel_pie(fig.add_subplot(gs[1, 0]), posts, cat_stats)
    panel_cat_bars(fig.add_subplot(gs[1, 1]), cat_stats)
    panel_eng_bars(fig.add_subplot(gs[2, 0]), cat_stats)
    panel_views_dist(fig.add_subplot(gs[2, 1]), posts)
    panel_dow_hour(fig.add_subplot(gs[3, :]), posts)
    panel_timeline(fig.add_subplot(gs[4, :]), posts)

    fig.savefig(FIGS / "00_dashboard.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def individual(posts, cat_stats, stats):
    # 01
    fig, ax = plt.subplots(figsize=(10, 7))
    panel_pie(ax, posts, cat_stats)
    fig.savefig(FIGS / "01_categories_pie.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 02
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6))
    panel_cat_bars(a1, cat_stats)
    panel_eng_bars(a2, cat_stats)
    fig.savefig(FIGS / "02_categories_bars.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 03
    fig, ax = plt.subplots(figsize=(14, 5))
    panel_dow_hour(ax, posts)
    fig.savefig(FIGS / "03_views_by_dow_hour.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 04
    fig, ax = plt.subplots(figsize=(14, 6))
    panel_timeline(ax, posts)
    fig.savefig(FIGS / "04_timeline_stacked.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 05
    fig, ax = plt.subplots(figsize=(8, 7))
    panel_top_emoji(ax, stats)
    fig.savefig(FIGS / "05_top_emoji.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 06
    fig, ax = plt.subplots(figsize=(9, 8))
    panel_top_domains(ax, stats)
    fig.savefig(FIGS / "06_top_domains.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # 07
    fig, ax = plt.subplots(figsize=(10, 5))
    panel_views_dist(ax, posts)
    fig.savefig(FIGS / "07_views_distribution.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    posts, cat_stats, stats, channel = load()
    dashboard(posts, cat_stats, stats, channel)
    individual(posts, cat_stats, stats)
    print(f"wrote {len(list(FIGS.glob('*.png')))} figures to {FIGS}")
    for p in sorted(FIGS.glob("*.png")):
        print(f"  {p.name}  ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
