# brazhniki-stats

Сбор и анализ статистики канала `@butterflies_and_berliners` через публичный превью `t.me/s/...` (без логина и API-ключей).

## Что внутри

### Скрипты
- `fetch.py` — скрейпер. Проходит `t.me/s/butterflies_and_berliners?before=<id>` с пагинацией, парсит id/дату/текст/views/реакции/медиа. Через `curl` subprocess (Python SSL ломается об MITM).
- `analyze.py` — считает общую статистику, рисует текстовый отчёт.
- `classify.py` — keyword-разметка постов по 10 тематическим категориям (music / cinema / theatre / exhibitions / parties_clubs / lectures / food_market / outdoor_sports / community_meta / other).
- `infographic.py` — рендерит PNG-инфографику через matplotlib.

### Данные
- `posts.jsonl` — все распарсенные посты (1 JSON на строку).
- `posts_cat.jsonl` — то же + категории и engagement.
- `channel.json` — счётчики канала (подписчики, фото, видео, ссылки).
- `stats.json` — агрегированная статистика (все числовое).
- `cat_stats.json` — аггрегаты по категориям.
- `raw_pages/` — кэш HTML-страниц (gitignored).
- `fetch.log` — лог сбора.

### Отчёты
- `report.md` — главный текстовый отчёт.
- `tops.md` — топ-25 по разным срезам (просмотры, реакции, engagement).
- `figs/00_dashboard.png` — главная инфографика (все панели в одной картинке).
- `figs/01..07_*.png` — отдельные панели.

## Как запустить с нуля

```bash
cd ~/brazhniki-stats
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python fetch.py        # ~1 минута — собирает все посты
.venv/bin/python analyze.py      # <1 сек — пересчитывает report/stats
.venv/bin/python classify.py     # <1 сек — размечает тематику
.venv/bin/python infographic.py  # ~3 сек — рендерит PNG в figs/
```

## Что отдаёт публичный превью

**Доступно:**
- id, дата (UTC), текст (HTML и plain)
- просмотры (на момент сбора)
- реакции (эмодзи + счётчик для каждого)
- медиа-тип (photo / video / voice / sticker / document / poll / link_preview)
- ссылки (href внутри поста), @-упоминания, хэштеги
- флаг "edited"

**Недоступно (нужен user-session через MTProto / MCP):**
- подписчики по дате (историческая кривая роста)
- кто подписался / отписался
- какие реакции кто поставил
- админ-лог канала
- комментарии к постам (их треды в linked chat)
- пересылки / фактические звонки
- если пост удалён — его прошлое содержимое

Для получения этих — см. ветку `telegram-mcp` ниже.

## Ограничения этого подхода

- Views и реакции — срез **на момент сбора**, не историческая динамика. Чтобы отслеживать рост конкретного поста — нужно пересобирать периодически и дифать `posts.jsonl`.
- Удалённые посты не восстанавливаются (из 561 id-слота существует 393, остальные 168 — удалены или service-сообщения вроде "Channel created").
- Публичный превью рендерится серверной стороной Telegram, он единый и стабильный, но Telegram может его менять без предупреждения — тогда ломаются regex в `fetch.py`.

## Альтернатива с полным доступом

Если нужны комменты, подписчики, админ-лог, историческая динамика — установить `mcp-telegram` и залогиниться своим аккаунтом:

```bash
claude mcp add telegram --scope user \
  -e TELEGRAM_API_ID=<id> -e TELEGRAM_API_HASH=<hash> \
  -- npx -y mcp-telegram
```

Потом перезапуск Claude Code и в новой сессии `login` → браузерный флоу.
