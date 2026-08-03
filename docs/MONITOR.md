# Website Monitor

The Altron monitor watches a webpage on a schedule, detects changes
(price drop, sale text, launch status, new listing, keyword appearance,
regex match) and notifies you through Telegram and/or email.

The monitor module is implemented as a regular `altron` subcommand so it
composes with the rest of the platform: every monitor is a small YAML
file, every run is recorded in SQLite, and the actual scheduler is
**your** OS — cron, systemd, Task Scheduler, or any container
orchestrator.

## Install

The monitor is **zero-dependency** — it uses only the standard library
plus what Altron already requires (pydantic, pyyaml). No `pip install`
step is needed beyond the base install:

```bash
pip install -e .
```

## Quickstart

```bash
# 1. Scaffold a monitor
altron monitor add \
  --name nike_drop \
  --url "https://www.nike.com/launch/air-max" \
  --interval 15m \
  --selector .ncss-btn-primary \
  --keyword "Dropping" --keyword "Sold Out" \
  --days "thu,fri,sat" --hours "09:00-21:00" --tz "Asia/Dubai" \
  --notify log

# 2. Dry-run to confirm it works
altron monitor run nike_drop --dry-run

# 3. Run for real once
altron monitor run nike_drop

# 4. Run every monitor in the directory
altron monitor run-all
```

The dry-run does everything *except* send notifications, so you can
iterate safely.

## YAML schema

A monitor file is a single mapping. See `examples/monitors/*.yaml` for
ready-to-use examples.

| Field | Type | Notes |
|---|---|---|
| `name` | slug | Unique within the directory. |
| `url` | URL | http(s) only. |
| `method` | GET/POST | Default GET. |
| `headers` | mapping | Extra request headers. |
| `timeout_seconds` | float | Default 20. |
| `interval` | `30s`/`15m`/`1h`/`1d` | For documentation only; cadence is set by your scheduler. |
| `active_from` / `active_until` | ISO date | Inclusive. |
| `days_of_week` | list of `mon..sun` | |
| `hours_of_day` | `HH:MM-HH:MM` (24h) | Local time in `timezone`; wraps midnight (e.g. `22:00-06:00`). |
| `timezone` | IANA name | Default `UTC`. |
| `selectors` | list of CSS-subset selectors | Each match's text is recorded. |
| `keywords` | list | Alert when any of these appear or disappear. |
| `regex` | regex string | A single regex; first few matches are reported. |
| `diff.full_page_hash` | bool | Compare full visible text by hash; default true. |
| `diff.ignore_selectors` | list | Remove before hashing (e.g. `nav`, `footer`, `#cookie-banner`). |
| `diff.min_change_chars` | int | Ignore tiny edits (whitespace jitter). Default 20. |
| `notify.channels` | list | One or more of `log`, `telegram`, `email`. |
| `notify.quiet_hours` | `HH:MM-HH:MM` | Buffer non-urgent alerts. |
| `notify.cooldown_seconds` | int | Suppress repeat alerts for the same `kind`. |
| `notify.urgent_keywords` / `notify.urgent_regex` | list | Bypass quiet hours and cooldown. |

### Supported selector syntax

The selector parser is intentionally tiny (stdlib-only). Each selector
is one of:

- `tag`           — e.g. `h1`, `article`
- `#id`           — e.g. `#price`
- `.class`        — e.g. `.price`, `.sale-banner`
- `tag.class`     — e.g. `span.price`
- `tag#id`        — e.g. `div#main`

XPath is not supported. If a site buries the value you want deep in
the DOM, point the monitor at the JSON endpoint the frontend uses
instead.

## Notification channels

Channels are configured by **environment variables only** — never put
tokens in YAML.

### Telegram

1. Talk to `@BotFather`, send `/newbot`, copy the token.
2. Send any message to your bot, then call
   `https://api.telegram.org/bot<token>/getUpdates` to find your `chat_id`.
3. Set in `.env`:
   ```
   ALTRON_TELEGRAM_BOT_TOKEN=...
   ALTRON_TELEGRAM_CHAT_ID=...
   ```

Test it: `altron monitor test-notify telegram`.

### Email (SMTP)

```
ALTRON_SMTP_HOST=smtp.gmail.com
ALTRON_SMTP_PORT=587
ALTRON_SMTP_USER=you@gmail.com
ALTRON_SMTP_PASSWORD=...            # Gmail: an App Password, not your real one
ALTRON_EMAIL_FROM=you@gmail.com
ALTRON_EMAIL_TO=you@gmail.com,partner@example.com
ALTRON_SMTP_TLS=1                   # 0 to disable STARTTLS
```

Test it: `altron monitor test-notify email`.

## Scheduling

`altron monitor run-all` does **one** pass and exits. Schedule it from
cron, systemd, or a container orchestrator. A 15-minute cadence is a
reasonable default:

```cron
*/15 * * * * cd /opt/altron && .venv/bin/altron monitor run-all >> data/monitor.log 2>&1
```

Windows Task Scheduler or a Kubernetes `CronJob` works the same way.

## Behaviour

- **First run** is a baseline: nothing is sent, the current state is
  recorded.
- **Subsequent runs** compare against the baseline. On any detected
  change, an alert is dispatched through every channel listed in
  `notify.channels`.
- **`cooldown_seconds`** prevents flapping.
- **`quiet_hours`** buffers non-urgent alerts. **Urgent keyword or
  regex matches** still go through.
- **State and history** live in SQLite (`data/monitor.sqlite` by
  default). You can inspect them with `altron monitor history <name>`.

## CLI reference

```
altron monitor list                 # list every YAML in --monitors-dir
altron monitor show <name>          # resolved config
altron monitor add …                # scaffold a YAML (see Quickstart)
altron monitor remove <name>        # delete YAML + clear its state
altron monitor run <name>           # one pass
altron monitor run <name> --dry-run # same, but no notifications
altron monitor run-all              # every active monitor, one pass
altron monitor history <name>       # recent alerts
altron monitor test-notify <ch>     # test a single channel
```

## Limitations

- **JavaScript-rendered pages are not supported.** The stdlib HTML
  parser only sees the raw bytes the server sends. If you need to
  monitor a JS-heavy site, find the JSON endpoint the frontend uses
  and point the monitor at that — those are usually faster and more
  reliable than the rendered HTML.
- The runner does not currently proxy through Tor. If you need to hide
  your IP from a site, set the `http_proxy` / `https_proxy`
  environment variables; `urllib` honours them automatically.
- The monitor records a 500-character excerpt of the most recent page
  text per run. Snapshots are intentionally not kept; the
  `data/monitor.sqlite` row stays under a kilobyte per monitor.

## Respect the sites you watch

Altron does its best to be a polite client (single in-flight request
per host, retries with backoff, realistic User-Agent). It is your
responsibility to comply with each site's Terms of Service,
robots.txt, and rate limits. Set a sensible `interval`, ignore noise
with `ignore_selectors`, and never use this to scrape data you are
not allowed to collect.
