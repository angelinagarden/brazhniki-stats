#!/usr/bin/env python3
"""
Build an interactive HTML landing page from the collected stats.

Design-system notes: inspired by gardenresearch.eu — tight typographic layout,
black/white with occasional yellow/blue highlights, Inter font, numbers as hero.

Output: landing/index.html (self-contained, opens with double click, uses CDN).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAND = HERE / "docs"
LAND.mkdir(exist_ok=True)

POSTS = HERE / "posts_cat.jsonl"
STATS = HERE / "stats.json"
CAT = HERE / "cat_stats.json"
CHAN = HERE / "channel.json"

RU_DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

CAT_COLORS = {
    "music":          "#e74c3c",
    "cinema":         "#f39c12",
    "theatre":        "#9b59b6",
    "exhibitions":    "#3498db",
    "parties_clubs":  "#1abc9c",
    "lectures":       "#95a5a6",
    "food_market":    "#e67e22",
    "outdoor_sports": "#27ae60",
    "community_meta": "#7f8c8d",
    "other":          "#bdc3c7",
}
CAT_LABELS = {
    "music":          "музыка",
    "cinema":         "кино",
    "theatre":        "театр",
    "exhibitions":    "выставки",
    "parties_clubs":  "клубы",
    "lectures":       "лекции",
    "food_market":    "еда",
    "outdoor_sports": "улица",
    "community_meta": "мета",
    "other":          "прочее",
}
CAT_ORDER = ["music", "cinema", "exhibitions", "parties_clubs", "theatre",
             "food_market", "lectures", "outdoor_sports", "community_meta", "other"]


def dt_local(iso: str) -> datetime:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    offset = 2 if 3 <= d.month <= 10 else 1
    return d.astimezone(timezone.utc).replace(tzinfo=None).replace(hour=(d.hour + offset) % 24)


def iso_week_key(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def build_data() -> dict:
    posts = [json.loads(l) for l in POSTS.open()]
    stats = json.loads(STATS.read_text())
    cat = json.loads(CAT.read_text())
    chan = json.loads(CHAN.read_text()) if CHAN.exists() else {}

    # ------- weekly stacked timeline by category -------
    weeks: dict[str, Counter] = defaultdict(Counter)
    for p in posts:
        d = dt_local(p["date"])
        weeks[iso_week_key(d)][p["primary_category"]] += 1
    week_keys = sorted(weeks.keys())
    timeline_series = {}
    for c in CAT_ORDER:
        if any(weeks[w][c] for w in week_keys):
            timeline_series[c] = [weeks[w][c] for w in week_keys]

    # ------- hour × dow heatmap -------
    heatmap: dict[tuple[int, int], int] = defaultdict(int)
    for p in posts:
        d = dt_local(p["date"])
        heatmap[(d.weekday(), d.hour)] += 1
    heat = [[d, h, c] for (d, h), c in heatmap.items()]

    # ------- top posts for each category (for cards) -------
    top_by_cat: dict[str, list[dict]] = {}
    for c in CAT_ORDER:
        items = [p for p in posts if p["primary_category"] == c]
        items.sort(key=lambda p: p["views"], reverse=True)
        top_by_cat[c] = [
            {
                "id": p["id"],
                "date": p["date"][:10],
                "text": (p["text"][:200] + ("…" if len(p["text"]) > 200 else "")),
                "views": p["views"],
                "rx": p["rx_sum"],
                "eng": round(p["engagement"] * 100, 2),
                "media": p["media_type"] or "text",
            }
            for p in items[:5]
        ]

    # ------- top-25 overall for a scrollable list -------
    all_top = sorted(posts, key=lambda p: p["views"], reverse=True)[:25]
    all_top_j = [
        {
            "id": p["id"],
            "date": p["date"][:10],
            "cat": p["primary_category"],
            "text": p["text"][:220] + ("…" if len(p["text"]) > 220 else ""),
            "views": p["views"],
            "rx": p["rx_sum"],
            "eng": round(p["engagement"] * 100, 2),
            "media": p["media_type"] or "text",
        }
        for p in all_top
    ]

    # ------- monthly avg views (for growth proxy) -------
    by_month: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        d = dt_local(p["date"])
        by_month[f"{d.year}-{d.month:02d}"].append(p["views"])
    monthly = sorted(by_month.items())
    monthly_series = {
        "months": [m for m, _ in monthly],
        "avg_views": [round(sum(vs)/len(vs)) for _, vs in monthly],
        "counts": [len(vs) for _, vs in monthly],
    }

    return {
        "channel": chan,
        "stats": stats,
        "cat": cat,
        "cat_order": CAT_ORDER,
        "cat_labels": CAT_LABELS,
        "cat_colors": CAT_COLORS,
        "timeline": {
            "week_keys": week_keys,
            "series": timeline_series,
        },
        "heatmap": heat,
        "top_by_cat": top_by_cat,
        "all_top": all_top_j,
        "ru_dow": RU_DOW,
        "monthly": monthly_series,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>brazhniki stats — @butterflies_and_berliners</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
:root{
  --fg:#000;
  --bg:#fff;
  --muted:#808080;
  --line:#000;
  --accent:#005DF0;
  --highlight:#FFF500;
  --inverse-bg:#000;
  --inverse-fg:#fff;
  --card-bg:#fafafa;
  --radius:0px;
  --maxw:1340px;
  --pad-x:32px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg);
  font-family:"Inter",system-ui,-apple-system,sans-serif;
  font-feature-settings:"ss01","cv11";
  -webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none}
a:hover{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px}

/* ---------- header ---------- */
.header{display:flex;justify-content:space-between;align-items:baseline;
  padding:20px var(--pad-x);border-bottom:1px solid var(--line);
  position:sticky;top:0;background:var(--bg);z-index:10}
.header .brand{font-weight:700;font-size:14px;letter-spacing:-.01em}
.header .nav{display:flex;gap:16px;font-size:14px;color:var(--muted)}
.header .nav a:hover{color:var(--fg)}

/* ---------- wrap ---------- */
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 var(--pad-x)}

/* ---------- hero ---------- */
.hero{padding:72px 0 48px;border-bottom:1px solid var(--line)}
.hero h1{font-weight:900;letter-spacing:-.03em;line-height:.95;
  font-size:clamp(44px,8vw,120px);margin:0 0 24px}
.hero .motto{font-weight:900;letter-spacing:-.02em;
  font-size:clamp(20px,2.4vw,32px);line-height:1.1;max-width:980px;color:#000}
.hero .motto .hl{background:var(--inverse-bg);color:var(--inverse-fg);padding:0 .15em}
.hero .motto .acc{background:var(--highlight);padding:0 .15em}
.hero .meta{display:flex;gap:24px;flex-wrap:wrap;margin-top:28px;
  font-family:"JetBrains Mono",ui-monospace,monospace;font-size:13px;color:var(--muted)}
.hero .meta b{color:var(--fg);font-weight:500}

/* ---------- kpi row ---------- */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:0;
  border-bottom:1px solid var(--line)}
.kpi{padding:28px 20px;border-right:1px solid var(--line);min-width:0;overflow:hidden}
.kpi:last-child{border-right:none}
.kpi .n{font-weight:900;font-size:clamp(28px,3.2vw,44px);
  letter-spacing:-.03em;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .l{font-size:11px;color:var(--muted);margin-top:8px;
  font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.03em;line-height:1.3}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}
  .kpi{border-right:none;border-bottom:1px solid var(--line)}
  .kpi .n{font-size:32px}}

/* ---------- sections ---------- */
section{padding:64px 0;border-bottom:1px solid var(--line)}
section h2{font-weight:900;font-size:clamp(32px,5vw,64px);
  letter-spacing:-.03em;margin:0 0 8px;line-height:.95}
section .lead{color:var(--muted);font-size:16px;max-width:720px;margin:0 0 36px}

/* ---------- cat chips ---------- */
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}
.chip{display:inline-flex;align-items:center;gap:6px;
  padding:6px 12px;border:1px solid var(--line);background:#fff;
  font-size:13px;cursor:pointer;transition:background .1s,color .1s}
.chip .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.chip.active{background:var(--fg);color:var(--bg)}
.chip:hover{background:var(--card-bg)}
.chip.active:hover{background:var(--fg)}

/* ---------- charts grid ---------- */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:0;
  border:1px solid var(--line)}
.grid-2 > div{padding:24px;border-right:1px solid var(--line)}
.grid-2 > div:last-child{border-right:none}
.grid-1{border:1px solid var(--line);padding:24px}
.chart{width:100%;height:420px}
.chart-tall{height:520px}
@media (max-width:900px){.grid-2{grid-template-columns:1fr}
  .grid-2 > div{border-right:none;border-bottom:1px solid var(--line)}
  .grid-2 > div:last-child{border-bottom:none}}

.chart-title{font-weight:700;font-size:18px;margin:0 0 4px;letter-spacing:-.01em}
.chart-sub{color:var(--muted);font-size:13px;margin:0 0 20px}

/* ---------- cat cards ---------- */
.cat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:16px;margin-top:24px}
.cat-card{border:1px solid var(--line);padding:20px;background:#fff;
  transition:transform .15s,box-shadow .15s}
.cat-card:hover{transform:translateY(-2px);box-shadow:4px 4px 0 var(--line)}
.cat-card .ch{display:flex;align-items:center;gap:8px;margin:0 0 12px}
.cat-card .ch .dot{width:14px;height:14px}
.cat-card .ch b{font-weight:700;font-size:16px}
.cat-card .nums{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
  padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  margin:0 0 12px;font-family:"JetBrains Mono",monospace;font-size:12px}
.cat-card .nums .v{font-weight:700;font-size:16px;letter-spacing:-.01em;color:var(--fg)}
.cat-card .nums .lbl{color:var(--muted);font-size:10px;text-transform:uppercase}
.cat-card .samples{font-size:12px;color:var(--muted);line-height:1.5}
.cat-card .samples a{display:block;padding:4px 0;border-bottom:1px dotted #ddd;color:var(--fg)}
.cat-card .samples a:last-child{border-bottom:none}

/* ---------- top posts list ---------- */
.toplist{border:1px solid var(--line)}
.toplist .row{display:grid;grid-template-columns:36px 110px 1fr 140px;
  gap:16px;padding:16px 20px;border-bottom:1px solid #eee;align-items:baseline}
.toplist .row:last-child{border-bottom:none}
.toplist .row:hover{background:var(--card-bg)}
.toplist .rank{font-weight:900;font-size:20px;letter-spacing:-.02em;color:var(--muted)}
.toplist .meta{font-family:"JetBrains Mono",monospace;font-size:11px;color:var(--muted)}
.toplist .meta .tag{display:inline-block;padding:2px 6px;background:var(--fg);color:var(--bg);
  font-size:10px;margin-right:4px}
.toplist .txt{font-size:14px;line-height:1.5;color:var(--fg)}
.toplist .nums{text-align:right;font-family:"JetBrains Mono",monospace;font-size:12px}
.toplist .nums .v{font-weight:700;font-size:16px;color:var(--fg);letter-spacing:-.01em}
@media (max-width:700px){.toplist .row{grid-template-columns:30px 1fr;grid-auto-rows:min-content}
  .toplist .meta,.toplist .nums{grid-column:2;text-align:left}}

/* ---------- emoji row ---------- */
.emoji-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:0;border:1px solid var(--line)}
.emoji-cell{padding:20px;text-align:center;border-right:1px solid var(--line);
  border-bottom:1px solid var(--line)}
.emoji-cell .e{font-size:36px;line-height:1}
.emoji-cell .c{font-family:"JetBrains Mono",monospace;font-size:12px;
  color:var(--muted);margin-top:6px}
.emoji-cell .c b{color:var(--fg);font-weight:700}

/* ---------- domain cols ---------- */
.dom-grid{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--line)}
.dom-grid > div{padding:24px;border-right:1px solid var(--line)}
.dom-grid > div:last-child{border-right:none}
.dom-list{list-style:none;padding:0;margin:0;font-size:14px}
.dom-list li{display:flex;justify-content:space-between;align-items:center;
  padding:8px 0;border-bottom:1px dotted #ddd}
.dom-list li:last-child{border-bottom:none}
.dom-list .b{height:4px;background:var(--fg);display:inline-block;margin-right:8px;
  vertical-align:middle}
.dom-list .n{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--muted)}
@media (max-width:700px){.dom-grid{grid-template-columns:1fr}
  .dom-grid > div{border-right:none;border-bottom:1px solid var(--line)}}

/* ---------- footer ---------- */
footer{padding:48px var(--pad-x);background:var(--inverse-bg);color:var(--inverse-fg)}
footer .foot-wrap{max-width:var(--maxw);margin:0 auto;display:grid;
  grid-template-columns:2fr 1fr 1fr;gap:32px}
footer h3{font-size:12px;text-transform:uppercase;letter-spacing:.1em;
  color:#888;margin:0 0 12px;font-weight:500}
footer p,footer a{color:var(--inverse-fg);font-size:14px;line-height:1.6}
footer .big{font-size:20px;line-height:1.3;font-weight:500;max-width:460px}
footer .legal{font-size:11px;color:#888;margin-top:40px;padding-top:20px;
  border-top:1px solid #333;max-width:var(--maxw);margin-left:auto;margin-right:auto}
@media (max-width:700px){footer .foot-wrap{grid-template-columns:1fr}}

/* ---------- utilities ---------- */
.mono{font-family:"JetBrains Mono",monospace}
.hl{background:var(--highlight)}
.inv{background:var(--inverse-bg);color:var(--inverse-fg);padding:1px 6px}
</style>
</head>
<body>
<header class="header">
  <div class="brand">brazhniki stats /</div>
  <nav class="nav">
    <a href="#overview">обзор</a>
    <a href="#topics">тематика</a>
    <a href="#when">когда</a>
    <a href="#reactions">реакции</a>
    <a href="#top">топ-посты</a>
    <a href="https://t.me/butterflies_and_berliners" target="_blank">канал →</a>
  </nav>
</header>

<main>
  <div class="wrap">
    <section class="hero" id="overview" style="border-bottom:none">
      <h1>Куда ходит<br>Берлин.</h1>
      <p class="motto">
        <span class="inv">@butterflies_and_berliners</span> &mdash; наша с командой <b>GENAU</b> афиша на&nbsp;<b>__SUBS__</b>&nbsp;подписчиков про&nbsp;
        <span class="hl">музыку,&nbsp;кино,&nbsp;клубы,&nbsp;выставки&nbsp;и&nbsp;театр</span>. Разобрали всё, что мы опубликовали за __DAYS__ дней.
      </p>
      <p class="meta">
        <span>Период:&nbsp;<b>__PERIOD__</b></span>
        <span>Собрано:&nbsp;<b>__POSTS__ постов</b></span>
        <span>Снято:&nbsp;<b>__GENERATED__</b></span>
        <span>Источник:&nbsp;<b>t.me/s/butterflies_and_berliners</b></span>
      </p>
    </section>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="n">__SUBS__</div><div class="l">подписчиков</div></div>
    <div class="kpi"><div class="n">__POSTS__</div><div class="l">постов за __DAYS__ дней</div></div>
    <div class="kpi"><div class="n" title="__TOTAL_VIEWS_FULL__">__TOTAL_VIEWS__</div><div class="l">суммарных просмотров</div></div>
    <div class="kpi"><div class="n" title="__TOTAL_RX_FULL__">__TOTAL_RX__</div><div class="l">реакций</div></div>
    <div class="kpi"><div class="n">__RATE__</div><div class="l">постов в день</div></div>
  </div>

  <div class="wrap">

    <section id="topics">
      <h2>О чём пишем.</h2>
      <p class="lead">Каждый наш пост размечен ключевыми словами по одной основной тематике из десяти. Multi-label возможен, но primary = max score. Правила разметки — в <code>classify.py</code>.</p>

      <div class="grid-2">
        <div>
          <p class="chart-title">Доля постов по тематике</p>
          <p class="chart-sub">наведись чтобы увидеть точные цифры и топ-пост в категории</p>
          <div id="chart-pie" class="chart"></div>
        </div>
        <div>
          <p class="chart-title">Средние просмотры и engagement</p>
          <p class="chart-sub">views — левая шкала (столбики), engagement = реакции/views — правая (точки)</p>
          <div id="chart-cat-bars" class="chart"></div>
        </div>
      </div>

      <div class="cat-grid" id="cat-cards"></div>
    </section>

    <section id="when">
      <h2>Когда постим.</h2>
      <p class="lead">Берлинское локальное время. Пик у нас в четверг днём (анонс выходных), сб-вс &mdash; почти не публикуем.</p>

      <div class="grid-1" style="margin-bottom:24px">
        <p class="chart-title">Карта нашей активности: день недели × час</p>
        <p class="chart-sub">цвет = количество постов в этом слоте</p>
        <div id="chart-heatmap" class="chart"></div>
      </div>

      <div class="grid-1" style="margin-bottom:24px">
        <p class="chart-title">Темп по неделям, стек по тематике</p>
        <p class="chart-sub">клики по легенде переключают серии; наведись на столбик — разбивка</p>
        <div id="chart-timeline" class="chart chart-tall"></div>
      </div>

      <div class="grid-1">
        <p class="chart-title">Наш охват по месяцам</p>
        <p class="chart-sub">средние просмотры поста (линия) и количество постов в месяц (столбики)</p>
        <div id="chart-monthly" class="chart"></div>
      </div>
    </section>

    <section id="reactions">
      <h2>На что реагируют читатели.</h2>
      <p class="lead">Наша фирменная реакция &mdash; <span class="hl">❤&zwj;🔥</span> (пламенное сердце), почти половина всех. Классический 👍 заметно ниже популярных эмоций — наше ядро не кивает нейтрально, оно влюбляется в эвент.</p>

      <div class="emoji-row" id="emoji-row"></div>
    </section>

    <section id="domains">
      <h2>Куда ведут наши ссылки.</h2>
      <p class="lead">Внешние домены, которые мы упоминаем в постах. Отдельно &mdash; упоминания @-каналов (включая ссылки на t.me/*).</p>

      <div class="dom-grid">
        <div>
          <p class="chart-title">Топ внешних доменов</p>
          <p class="chart-sub">без t.me (внутрителеграмные линки)</p>
          <ul class="dom-list" id="dom-list"></ul>
        </div>
        <div>
          <p class="chart-title">Топ @-упоминаний</p>
          <p class="chart-sub">включая ссылки вида t.me/channel</p>
          <ul class="dom-list" id="mention-list"></ul>
        </div>
      </div>
    </section>

    <section id="top">
      <h2>Наш топ-25 по просмотрам.</h2>
      <p class="lead">Самые популярные наши посты за весь период. Клик по заголовку &mdash; открыть в Telegram.</p>
      <div class="toplist" id="toplist"></div>
    </section>

    <section>
      <h2>Как мы это собрали.</h2>
      <p class="lead" style="max-width:860px">
        Данные собраны с публичного превью <code>t.me/s/butterflies_and_berliners?before=&lt;id&gt;</code> &mdash; без логина, без MCP, без API-ключей. Все просмотры и реакции &mdash; срез на момент сбора; историческая динамика недоступна в превью.
        <br><br>
        Исходники (fetch, analyze, classify, build_landing) лежат в <a href="https://github.com/angelinagarden/brazhniki-stats" target="_blank">github.com/angelinagarden/brazhniki-stats</a>. Весь пайплайн &mdash; четыре Python-скрипта, воспроизводимо из requirements.txt.
      </p>
    </section>
  </div>
</main>

<footer>
  <div class="foot-wrap">
    <div>
      <p class="big">brazhniki stats &mdash; срез на __GENERATED__.<br>Собрали локально, без админ-доступа к каналу — только публичный превью.</p>
    </div>
    <div>
      <h3>Наш канал</h3>
      <p><a href="https://t.me/butterflies_and_berliners" target="_blank">@butterflies_and_berliners</a></p>
      <p>__SUBS__ подписчиков</p>
      <p style="color:#888">команда GENAU</p>
    </div>
    <div>
      <h3>Контакт</h3>
      <p><a href="mailto:a@gardenresearch.eu">a@gardenresearch.eu</a></p>
      <p><a href="https://gardenresearch.eu" target="_blank">gardenresearch.eu</a></p>
    </div>
  </div>
  <p class="legal">© 2026 · brazhniki-stats · данные с публичного превью t.me, обновляется ручным запуском pipeline</p>
</footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const fmt = n => (n||0).toLocaleString('ru-RU').replace(/,/g,' ');
const catLabel = c => D.cat_labels[c] || c;
const catColor = c => D.cat_colors[c] || '#999';

// -------- pie chart --------
(function(){
  const present = D.cat_order.filter(c => (D.cat.categories[c]?.count||0) > 0);
  const data = present.map(c => ({
    name: catLabel(c),
    value: D.cat.categories[c].count,
    itemStyle: {color: catColor(c)},
    _cat: c,
  }));
  const chart = echarts.init(document.getElementById('chart-pie'));
  chart.setOption({
    tooltip:{trigger:'item',
      formatter: p => {
        const s = D.cat.categories[p.data._cat];
        return `<b>${p.name}</b> &mdash; ${p.value} постов (${s.share}%)<br>`
             + `avg views: <b>${fmt(s.avg_views)}</b><br>`
             + `avg reactions: <b>${s.avg_reactions}</b><br>`
             + `engagement: <b>${s.avg_engagement_pct}%</b>`;
      }},
    legend:{bottom:0, textStyle:{fontFamily:'Inter',fontSize:12},itemHeight:10,itemGap:12},
    series:[{
      type:'pie', radius:['42%','72%'], center:['50%','44%'],
      avoidLabelOverlap:true,
      itemStyle:{borderColor:'#fff',borderWidth:2},
      label:{show:true,formatter:'{b}\n{d}%',fontFamily:'Inter',fontSize:11,color:'#000'},
      data,
    }]
  });
  window.addEventListener('resize',()=>chart.resize());
})();

// -------- category bars (views + engagement combo) --------
(function(){
  const present = D.cat_order.filter(c => (D.cat.categories[c]?.count||0) > 0);
  const avgViews = present.map(c => D.cat.categories[c].avg_views);
  const eng = present.map(c => D.cat.categories[c].avg_engagement_pct);
  const chart = echarts.init(document.getElementById('chart-cat-bars'));
  chart.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'},
      formatter: args => {
        const i = args[0].dataIndex;
        const c = present[i];
        const s = D.cat.categories[c];
        return `<b>${catLabel(c)}</b> &mdash; ${s.count} постов<br>`
          + `avg views: <b>${fmt(s.avg_views)}</b><br>`
          + `avg reactions: <b>${s.avg_reactions}</b><br>`
          + `engagement: <b>${s.avg_engagement_pct}%</b>`;
      }},
    legend:{bottom:0,textStyle:{fontFamily:'Inter'}},
    grid:{left:70,right:60,bottom:50,top:20},
    xAxis:{type:'category',data:present.map(catLabel),
      axisLabel:{rotate:30,fontFamily:'Inter',color:'#333'}},
    yAxis:[
      {type:'value',name:'avg views',
        axisLabel:{formatter:v=>v>=1000?(v/1000)+'K':v,fontFamily:'JetBrains Mono'},
        splitLine:{lineStyle:{color:'#eee'}}},
      {type:'value',name:'engagement %',
        axisLabel:{formatter:'{value}%',fontFamily:'JetBrains Mono'},
        splitLine:{show:false}},
    ],
    series:[
      {name:'avg views',type:'bar',yAxisIndex:0,
        data:avgViews.map((v,i)=>({value:v,itemStyle:{color:catColor(present[i])}})),
        barWidth:'50%'},
      {name:'engagement %',type:'line',yAxisIndex:1,
        data:eng,
        symbol:'circle',symbolSize:10,
        lineStyle:{width:2,color:'#000'},
        itemStyle:{color:'#000'}},
    ],
  });
  window.addEventListener('resize',()=>chart.resize());
})();

// -------- cat cards --------
(function(){
  const root = document.getElementById('cat-cards');
  const present = D.cat_order.filter(c => (D.cat.categories[c]?.count||0) > 0);
  for (const c of present) {
    const s = D.cat.categories[c];
    const tops = (D.top_by_cat[c]||[]).slice(0,3);
    const samples = tops.map(p => `
      <a href="https://t.me/butterflies_and_berliners/${p.id}" target="_blank" title="${p.text.replace(/"/g,'&quot;')}">
        <span class="mono">#${p.id}</span> &middot; ${fmt(p.views)} views &middot; <span>${p.text.slice(0,80)}${p.text.length>80?'…':''}</span>
      </a>`).join('');
    const el = document.createElement('div');
    el.className = 'cat-card';
    el.innerHTML = `
      <div class="ch">
        <span class="dot" style="background:${catColor(c)}"></span>
        <b>${catLabel(c)}</b>
        <span style="color:var(--muted);font-size:12px;margin-left:auto" class="mono">${s.share}%</span>
      </div>
      <div class="nums">
        <div><div class="v">${s.count}</div><div class="lbl">постов</div></div>
        <div><div class="v">${fmt(s.avg_views)}</div><div class="lbl">avg views</div></div>
        <div><div class="v">${s.avg_engagement_pct}%</div><div class="lbl">engage</div></div>
      </div>
      <div class="samples">${samples}</div>
    `;
    root.appendChild(el);
  }
})();

// -------- heatmap --------
(function(){
  const chart = echarts.init(document.getElementById('chart-heatmap'));
  const maxV = Math.max(...D.heatmap.map(r=>r[2]));
  chart.setOption({
    tooltip:{position:'top',
      formatter: p => `<b>${D.ru_dow[p.data[0]]} ${String(p.data[1]).padStart(2,'0')}:00</b><br>${p.data[2]} постов`},
    grid:{left:50,right:40,top:30,bottom:40},
    xAxis:{type:'category',data:Array.from({length:24},(_,i)=>String(i).padStart(2,'0')),
      splitArea:{show:false},axisLabel:{fontFamily:'JetBrains Mono'}},
    yAxis:{type:'category',data:D.ru_dow,splitArea:{show:false},
      axisLabel:{fontFamily:'Inter'}},
    visualMap:{min:0,max:maxV,calculable:true,orient:'horizontal',left:'center',bottom:0,
      inRange:{color:['#fff','#fff5e6','#ffb84d','#e74c3c','#000']}},
    series:[{
      type:'heatmap',
      data:D.heatmap.map(r=>[r[1],r[0],r[2]]),  // [x=hour, y=dow, val]
      label:{show:true,formatter: p => p.data[2]>0 ? p.data[2]:'',color:'#000',fontSize:10},
      emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}},
    }],
  });
  window.addEventListener('resize',()=>chart.resize());
})();

// -------- weekly timeline stacked --------
(function(){
  const chart = echarts.init(document.getElementById('chart-timeline'));
  const cats = Object.keys(D.timeline.series);
  const series = cats.map(c => ({
    name: catLabel(c),
    type:'bar', stack:'t',
    data: D.timeline.series[c],
    itemStyle:{color:catColor(c)},
  }));
  chart.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},
    legend:{bottom:0,textStyle:{fontFamily:'Inter'},type:'scroll'},
    grid:{left:50,right:30,top:20,bottom:70},
    xAxis:{type:'category',data:D.timeline.week_keys,
      axisLabel:{fontFamily:'JetBrains Mono',fontSize:10,
        formatter: v => v.replace(/^20/,'')}},
    yAxis:{type:'value',name:'постов/нед',splitLine:{lineStyle:{color:'#eee'}},
      axisLabel:{fontFamily:'JetBrains Mono'}},
    series,
  });
  window.addEventListener('resize',()=>chart.resize());
})();

// -------- monthly avg views + count --------
(function(){
  const chart = echarts.init(document.getElementById('chart-monthly'));
  chart.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'cross'}},
    legend:{bottom:0,textStyle:{fontFamily:'Inter'}},
    grid:{left:60,right:60,top:20,bottom:50},
    xAxis:{type:'category',data:D.monthly.months,
      axisLabel:{fontFamily:'JetBrains Mono'}},
    yAxis:[
      {type:'value',name:'avg views',axisLabel:{formatter:v=>v>=1000?(v/1000)+'K':v,fontFamily:'JetBrains Mono'},splitLine:{lineStyle:{color:'#eee'}}},
      {type:'value',name:'постов',axisLabel:{fontFamily:'JetBrains Mono'},splitLine:{show:false}},
    ],
    series:[
      {name:'avg views',type:'line',data:D.monthly.avg_views,
        smooth:true,lineStyle:{width:3,color:'#000'},
        itemStyle:{color:'#000'},symbol:'circle',symbolSize:10,
        yAxisIndex:0, areaStyle:{color:'rgba(0,0,0,0.08)'}},
      {name:'постов/месяц',type:'bar',data:D.monthly.counts,
        yAxisIndex:1, barWidth:'30%',itemStyle:{color:'#f39c12'}},
    ],
  });
  window.addEventListener('resize',()=>chart.resize());
})();

// -------- emoji row --------
(function(){
  const root = document.getElementById('emoji-row');
  const emo = D.stats.reactions.top_emoji.slice(0,15);
  for (const [e,c] of emo) {
    const el = document.createElement('div');
    el.className = 'emoji-cell';
    el.innerHTML = `<div class="e">${e}</div><div class="c"><b>${fmt(c)}</b></div>`;
    root.appendChild(el);
  }
})();

// -------- domain + mention lists --------
(function(){
  const root = document.getElementById('dom-list');
  const dom = D.stats.top_domains.filter(d => d[0] !== 't.me').slice(0,20);
  const maxV = Math.max(...dom.map(d => d[1]));
  for (const [d,c] of dom) {
    const li = document.createElement('li');
    li.innerHTML = `<span><span class="b" style="width:${Math.round(c/maxV*120)}px"></span>${d}</span><span class="n">${c}</span>`;
    root.appendChild(li);
  }
  const root2 = document.getElementById('mention-list');
  const men = D.stats.top_mentions.filter(m => m[0] !== '@butterflies_and_berliners').slice(0,20);
  const maxM = Math.max(...men.map(d => d[1]));
  for (const [m,c] of men) {
    const li = document.createElement('li');
    li.innerHTML = `<span><span class="b" style="width:${Math.round(c/maxM*120)}px"></span>${m}</span><span class="n">${c}</span>`;
    root2.appendChild(li);
  }
})();

// -------- top-25 list --------
(function(){
  const root = document.getElementById('toplist');
  for (let i=0;i<D.all_top.length;i++) {
    const p = D.all_top[i];
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
      <div class="rank">${i+1}</div>
      <div class="meta">
        <span class="tag" style="background:${catColor(p.cat)};color:#fff">${catLabel(p.cat)}</span><br>
        ${p.date}<br>${p.media}
      </div>
      <div class="txt">
        <a href="https://t.me/butterflies_and_berliners/${p.id}" target="_blank">${p.text.replace(/</g,'&lt;')}</a>
      </div>
      <div class="nums">
        <div class="v">${fmt(p.views)}</div><div>views</div>
        <div style="margin-top:6px"><b>${fmt(p.rx)}</b> rx &middot; ${p.eng}% eng</div>
      </div>
    `;
    root.appendChild(row);
  }
})();
</script>
</body>
</html>
"""


def main() -> int:
    d = build_data()

    stats = d["stats"]
    chan = d["channel"]
    html = HTML_TEMPLATE

    def compact(n: int) -> str:
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f}M".rstrip("0").rstrip(".") + ("M" if not str(n/1_000_000).endswith(".0") else "")
        if n >= 1_000:
            return f"{n/1_000:.1f}K".rstrip("0").rstrip(".") + ("K" if not str(n/1_000).endswith(".0") else "")
        return str(n)

    def compact2(n: int) -> str:
        if n >= 1_000_000:
            v = n / 1_000_000
            return (f"{v:.2f}" if v < 10 else f"{v:.1f}").rstrip("0").rstrip(".") + "M"
        if n >= 10_000:
            return f"{round(n/1000)}K"
        if n >= 1_000:
            v = n / 1000
            return f"{v:.1f}K"
        return str(n)

    repl = {
        "__SUBS__":         chan.get("subscribers", "?"),
        "__POSTS__":        str(stats["posts_total"]),
        "__DAYS__":         str(stats["days_covered"]),
        "__PERIOD__":       f'{stats["date_range"][0][:10]} — {stats["date_range"][1][:10]}',
        "__TOTAL_VIEWS__":  compact2(stats['views']['total']),
        "__TOTAL_VIEWS_FULL__":  f"{stats['views']['total']:,}".replace(",", " "),
        "__TOTAL_RX__":     compact2(stats['reactions']['total']),
        "__TOTAL_RX_FULL__":     f"{stats['reactions']['total']:,}".replace(",", " "),
        "__RATE__":         str(stats["posts_per_day_avg"]),
        "__GENERATED__":    d["generated_at"],
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    data_json = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("__DATA__", data_json)

    (LAND / "index.html").write_text(html)
    print(f"wrote {LAND/'index.html'}  ({len(html)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
