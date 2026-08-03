---
description: Add, list, run, and troubleshoot website monitors that alert you on price drops, sales, launches, new listings, or any change.
---

# Website Monitor Skill

You are operating the **Altron website monitor**: a scheduled, rules-driven
watcher that fetches a page, compares it to the last seen state, and
immediately notifies the user through Telegram or email when something
changes.

The skill is a thin conversation layer on top of a real, working Python
module under `src/altron/monitor/`. The monitor uses only the standard
library — no third-party HTTP client, no HTML parser dependency, no
`pip install` step required.

## Subcommands (mirror the CLI exactly)

| User says something like… | You should run |
|---|---|
| "add a monitor for X" / "watch this page" | `altron monitor add --name <slug> --url <url> [--selector …] [--keywords …] [--interval 15m] [--days …] [--hours …]` then edit the produced YAML |
| "list my monitors" | `altron monitor list` |
| "show monitor details" | `altron monitor show <name>` |
| "test this monitor" | `altron monitor run <name> --dry-run` |
| "run all monitors now" | `altron monitor run-all` |
| "delete a monitor" | `altron monitor remove <name>` |
| "set up Telegram" / "set up email" | show the matching "Setup" section below |
| "what changed lately?" | `altron monitor history <name> [--limit N]` |
| "is it working?" / "test my channels" | `altron monitor test-notify <channel>` |

## YAML shape (always show this when adding/editing)

```yaml
name: nike-airmax-sale            # required, unique slug
url: https://www.nike.com/launch/air-max
method: GET                        # GET or POST
headers: { }                       # optional extra headers
interval: 15m                      # 15m, 1h, 6h, 1d  (cron-driven; see notes)
# active window — the monitor only fires inside this window
active_from: 2026-08-01            # ISO date, inclusive (optional)
active_until: 2026-12-31           # ISO date, inclusive (optional)
days_of_week: [mon, tue, wed, thu, fri, sat, sun]   # optional
hours_of_day: "09:00-21:00"        # local time, 24h, optional
timezone: Asia/Dubai               # IANA name; defaults to UTC

# what to look for — pick one or combine
selectors:                         # CSS subset: tag, #id, .class, tag.class
  - .product-price
  - "#availability"
keywords:                          # alert when any of these appear or disappear
  - sale
  - "out of stock"
  - "in stock"
regex: 'EUR\s*[0-9]+[.,]?[0-9]*'   # optional regex; first few matches reported

# how to compare
diff:
  full_page_hash: true             # alert on any meaningful text change
  ignore_selectors: [nav, footer, "#cookie-banner"]  # noise to strip
  min_change_chars: 20             # ignore tiny edits (whitespace jitter)

# where to send the alert
notify:
  - telegram                       # name only; credentials live in .env
  - email
quiet_hours: "23:00-07:00"         # buffer non-urgent alerts instead of sending
cooldown: 30m                      # suppress repeat alerts for the same change
```

Supported selector syntax is intentionally tiny: a tag name, an `#id`, a
`.class`, or `tag.class` / `tag#id`. XPath is not supported. The
trade-off is "no BeautifulSoup / lxml dependency" — the standard library
`HTMLParser` is enough for selector matching and text extraction.

## Setup (channel credentials go in `.env`, never in YAML)

Show this verbatim when the user asks to set up a channel. Do **not** put
tokens in the YAML.

- **Telegram** — create a bot with `@BotFather`, get the token, message
  the bot once, then call
  `https://api.telegram.org/bot<token>/getUpdates` to find your `chat_id`.
  Set in `.env`:
  ```
  ALTRON_TELEGRAM_BOT_TOKEN=…
  ALTRON_TELEGRAM_CHAT_ID=…
  ```
- **Email (SMTP)** — for Gmail use an *App Password*, not your real
  password:
  ```
  ALTRON_SMTP_HOST=smtp.gmail.com
  ALTRON_SMTP_PORT=587
  ALTRON_SMTP_USER=you@gmail.com
  ALTRON_SMTP_PASSWORD=…            # app password
  ALTRON_EMAIL_FROM=you@gmail.com
  ALTRON_EMAIL_TO=you@gmail.com,partner@example.com
  ```

## Scheduling (the recommended pattern)

`altron monitor run-all` does **one** pass over every monitor that is
currently inside its active window, sends notifications, and exits.
Schedule it from cron or systemd at the smallest interval you care about.
A 15-minute cadence covers the example YAML above:

```cron
*/15 * * * * cd /home/user/Altron && /home/user/Altron/.venv/bin/altron monitor run-all >> /home/user/Altron/data/monitor.log 2>&1
```

Windows users can use Task Scheduler with the same command. The CLI
itself does not loop — keeping it cron-friendly means it survives
reboots, container restarts, and works well on a cheap VPS.

## Behaviour the user should know

- **First run** is a baseline: nothing is sent, the current state is
  recorded.
- **Second run onward** compares against the baseline; on any detected
  change a notification is dispatched through every channel listed under
  `notify:`.
- **`cooldown`** prevents flapping — if the page keeps changing back and
  forth, the user gets one alert per `cooldown` window per change kind.
- **`quiet_hours`** buffers non-urgent alerts and sends a single digest
  at the end of the window. Urgent keyword matches (e.g. `out of stock`
  disappearing) bypass quiet hours.
- **Rate limits and politeness** are built in: 1 request per host per
  interval, configurable per-monitor timeout, retries with exponential
  backoff, and a realistic `User-Agent`. The user is responsible for
  respecting each site's Terms of Service.

## When the user reports a problem

1. Run `altron monitor show <name>` to print the resolved config.
2. Run `altron monitor run <name> --dry-run` to see what would be
   detected without sending notifications.
3. Run `altron monitor test-notify <channel>` to confirm the channel
   works.
4. If the page is JS-heavy, the stdlib HTML parser will not see the
   rendered content. Tell the user that JS rendering is not supported
   in this build and suggest either (a) finding the JSON endpoint the
   frontend uses and pointing the monitor at that, or (b) using a
   server-side prerender service.
5. If the site blocks bots, suggest setting custom `headers:` (Cookie,
   UA) and remind the user to respect the site's ToS.

## What you must NOT do

- Do not invent CLI flags. If a user asks for something the CLI doesn't
  support, explain the gap and offer to add it to the module — don't
  fake it.
- Do not commit `.env` or any file containing real tokens. The
  `.gitignore` already covers it; double-check before staging.
- Do not run monitors in a tight loop from inside the skill — always
  point the user at cron/systemd so the process is restart-safe.
- Do not promise JS rendering. The stdlib parser only sees what the
  server sent.
