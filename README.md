# SSL Checker

Utility for checking TLS certificate expiration on hosts: TLS connection, certificate reading, remaining **calendar** days calculation, optional notifications (Windows and corporate HTTP API), batch reports, and daily schedule mode. By default, **nothing is sent** to the corporate API if all hosts are fully "OK"; a message is sent only when there is a reason (expired or warning thresholds, check error, trust chain issue) or with the **`--notify-always`** flag (see below). Container launch on Linux is described in the [Docker on Linux](#docker-on-linux) section.

Entry point: `main.py` and the **`ssl-checker`** console command (see `[project.scripts]` in `pyproject.toml`).

## Features

| Area | Description |
|------|-------------|
| **TLS** | Connect to host:port, 10s timeout; trust chain verification per `TLS_*` settings in `.env`. |
| **Expiry** | `notBefore` / `notAfter` dates, remaining calendar days; on partial trust chain failure, optionally read only the expiry from the certificate (`TLS_READ_EXPIRY_ON_VERIFY_FAIL`). |
| **Host List** | `SITES_TO_CHECK` in `.env` and/or `SITES_FILE` (file takes priority if it exists); format `host` or `host:port`. |
| **One-time Check** | Single host (`--site`) or entire list from `.env` without `--site`. |
| **JSON** | Flag `--json`: output to stdout as a single object or array. |
| **Batch (`--batch`)** | All hosts, summary Markdown report to **log always**; to corporate HTTP API (when configured) — **only if there is a reason** for at least one host (expired or expiring today, below `WARN_DAYS` / `CRITICAL_DAYS`, TLS/network error, unverified trust chain). On full "OK" for the list, **nothing is sent** to the API unless **`--notify-always`** is set (then a full report is sent, including for channel debugging). Exit code `1` if at least one host **requires attention** (same conditions as for API), otherwise `0`. |
| **Scheduler (`--schedule`)** | Long-running process: daily cron + optional first batch check on start; remote API rules are **as in `--batch`**, the **`--notify-always`** flag is **not available** here — cannot force "all OK" to API. Typical container scenario — see [Docker on Linux](#docker-on-linux). |
| **Windows Notifications** | Window/message on check error, expired/thresholds `WARN_DAYS` / `CRITICAL_DAYS`, chain warning (`SEND_WIN_ALERT`, `WIN_USE_NATIVE_MSGBOX`). |
| **Corporate API** | `POST {NOTIFICATION_API_BASE_URL}/api/v1/notifications` when fully configured in `.env` (`SEND_NOTIFICATIONS` and related variables). |
| **Logs** | Loguru, `./logs` directory or `LOGS_DIR` from `.env`. |

Check logic: `core/ssl_cert_monitor.py`; batch and report: `core/batch_report.py`; status rules and thresholds: `core/status_policy.py`; error texts for report and UI: `core/error_messages.py`; settings: `config/settings.py`.

## Requirements

- Python **3.12+**
- Recommended: **[uv](https://docs.astral.sh/uv/)** for development and running from sources.

## Install Dependencies

In the repository root:

```bash
uv sync
```

Alternative without uv: create a virtual environment and `pip install .` (after that `ssl-checker` appears in `Scripts`).

## Configuration via `.env`

Parameters are read via `python-dotenv`. The process working directory must contain the `.env` file (or environment variables are set otherwise).

1. Copy the template:

```bash
copy .env.example .env
```

2. Edit `.env` (host list, thresholds, TLS, notifications, scheduler).

Full list of variables see in `.env.example` and comments in `config/settings.py`.

## CLI: `ssl-checker` Command

After `uv sync`, run from the project root:

```bash
uv run ssl-checker --help
```

Equivalent:

```bash
uv run python main.py --help
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--site HOST_OR_URL` | Single host or URL (with port in URL if non-standard needed). **Without** `--site`, the entire list from `SITES_TO_CHECK` / `SITES_FILE` is checked. |
| `--port N` | TLS port if `--site` has no port (default from `.env`: `SITE_PORT`, usually 443). |
| `--json` | Output result to **stdout** in JSON (single object for one host, array for multiple). Without `--json` — human-readable output to log and dialogs/notifications per application rules. |
| `--notify-always` | Force send notification to corporate API/Mattermost **even if everything is fine** (channel debugging). With **`--batch`** — full summary report; for one-time check without `--batch` — message to API even with "green" certificate (Windows window on full OK is not shown). **Incompatible** with `--schedule`. |
| `--batch` | One run: all hosts from list, summary report to log; to API — only if there is **a reason** for hosts (see [API / Mattermost Notifications](#api--mattermost-notifications)) unless **`--notify-always`** is set. **Incompatible** with `--site`. Exit code: `0` — all hosts without issues (expiry and chain), `1` — at least one host requires attention (expired, thresholds, chain, TLS/network error, etc.). |
| `--lang EN\|RU` | Interface language (default from `LANGUAGE` in `.env` or `ru`). |
| `--schedule` | Scheduler: every day at time from `.env`, optional batch on start. **Incompatible** with `--site`, `--json`, and `--notify-always`. |

Modes `--batch` and `--schedule` are mutually exclusive (group in `argparse`).

### CLI Examples

```bash
uv run ssl-checker
uv run ssl-checker --site ias.energo.net --port 443
uv run ssl-checker --site https://example.com:8443 --json
uv run ssl-checker --json
uv run ssl-checker --batch
uv run ssl-checker --batch --notify-always
uv run ssl-checker --schedule
```

- Without `--site`: list is read from `.env`; if after token parsing the list is **empty** (`SITES_TO_CHECK` is empty and `SITES_FILE` is missing/empty) — the program exits with an error; set at least one host (see `.env.example`).
- With `--site`: list from `.env` for this run is **not mixed in** — only the specified host is checked (after URL/host normalization).

### API / Mattermost Notifications

When `SEND_NOTIFICATIONS=true` and a full set of API fields, the logic is: **"quiet" success to API is not sent** — the request goes only if there is a **reason** for a host **or** forced mode is enabled (where supported).

**Reason for remote notification** (same meaning as for windows/statuses in `core/status_policy.py`):

- expired or **0** calendar days remaining (expires on check day);
- expiry in critical or warning threshold zone: less than `CRITICAL_DAYS` or less than `WARN_DAYS` (see `.env`);
- **error** checking host (TLS, network, could not read certificate, etc.);
- expiry is still "green" but **trust chain** to issuer is not verified.

Further by modes:

- **One-time check** (without `--batch`): for each host from the run, message to API goes **only on reason** from the list above; on fully "green" certificate, **nothing is sent** to API (only log). The **`--notify-always`** flag adds sending on full OK (Windows window on full OK is still not shown).
- **`--batch`**: summary to log always; to API — **only if there is at least one host with a reason**, otherwise silence. **`--batch --notify-always`** — one forced report to API even on full OK for all hosts.
- **`--schedule`**: like **`--batch`** for API rules, but **`--notify-always` is not available** — in schedule you cannot request notification "just in case" on full OK.

### Global `ssl-checker` Command in System

To make `ssl-checker --help` work from any directory:

1. **[pipx](https://pipx.pypa.io/)** (isolated install to PATH):

   ```bash
   pipx install /path/to/ssl_checker
   ```

2. **[uv tool](https://docs.astral.sh/uv/guides/tools/)**:

   ```bash
   uv tool install /path/to/ssl_checker
   ```

3. Add to **PATH** the `bin` / `Scripts` directory of the project's virtual environment (e.g. `.../ssl_checker/.venv/bin` on Linux or `...\ssl_checker\.venv\Scripts` on Windows) after `uv sync`.

In all cases, make sure that on launch the process "sees" the needed `.env` (run from directory with `.env` or environment variables set in advance).

## Daily Run on Windows without Docker

Once a day via Task Scheduler is enough to run the batch check, without a long-running process.

1. Configure `.env`: host list, optionally `SEND_NOTIFICATIONS` and API fields.
2. **Task Scheduler** → create task → trigger "daily".
3. Action: `cmd.exe` with `/c` and path to `scripts\run_daily.cmd`.
4. Working folder: project root (where `.env` and `pyproject.toml`).

`run_daily.cmd` calls `uv run python main.py --batch` (to API — only on reasons for hosts or with **`--notify-always`**). To test the channel on a "green" list, temporarily add **`--notify-always`** to `--batch`. In **`--schedule`** (Docker) there is no forced sending on full OK. For long-running scheduler in container on Linux see [Docker on Linux](#docker-on-linux).

## Notification Service (HTTP)

Request: `POST {NOTIFICATION_API_BASE_URL}/api/v1/notifications` with JSON body (`title`, `text`, `deliverToMattermost`, `userSids`) and headers **`clientSecretKey`**, **`appLabel`**. The `link` field is **not sent** by the client (so that no empty link appears in Mattermost).

Minimum for sending: `SEND_NOTIFICATIONS=true`, URL, key, label and **at least one** ID in `NOTIFICATION_USER_IDS` are set. The `deliverToMattermost` flag in JSON is set by the **`NOTIFICATION_DELIVER_TO_MATTERMOST`** variable (default `true`).

`NOTIFICATION_API_TLS_VERIFY` — TLS verification on outgoing POST: `true` / `false` / path to PEM of issuer's root certificate.

## Main `.env` Variables

| Variable | Purpose |
|----------|---------|
| `SITE_PORT` | Default TLS port for hosts without `:port`. |
| `LOGS_DIR` | Log directory; empty = `./logs` next to project. |
| `SITES_TO_CHECK`, `SITES_FILE` | Host list for normal run and `--batch`. |
| `WARN_DAYS`, `CRITICAL_DAYS` | Warning thresholds (calendar days). |
| `SEND_WIN_ALERT`, `WIN_USE_NATIVE_MSGBOX` | Windows windows. |
| `SEND_NOTIFICATIONS`, `NOTIFICATION_*` | Corporate API notifications; separately: `NOTIFICATION_DELIVER_TO_MATTERMOST` — Mattermost delivery. |
| `TLS_VERIFY` | `true` / `false` / path to PEM: trust to host chain. |
| `TLS_SITE_CHECK_TRUST_ONLY_CAFILE` | Only PEM from `TLS_VERIFY`, no system store. |
| `TLS_READ_EXPIRY_ON_VERIFY_FAIL` | After verify error, retry without verification and read only expiry. |
| `SCHEDULER_TIMEZONE` | IANA timezone for `--schedule`; `tzdata` package is installed in Docker image (see Dockerfile). |
| `DAILY_BATCH_HOURS` | Hours for daily batch in `--schedule` mode (comma-separated, e.g. `9,15,21`; runs at :00). |
| `LANGUAGE` | Interface language: `en` or `ru` (default). |
| `RUN_BATCH_ON_START` | Run batch immediately on scheduler start (`true`/`false`). |

## Module Structure

- `main.py` — CLI and mode routing.
- `core/models.py` — models and error codes.
- `core/site_list.py` — host list parsing.
- `core/ssl_cert_monitor.py` — TLS and certificate check.
- `core/batch_report.py` — batch and report text.
- `core/daily_scheduler.py` — APScheduler, `--schedule` mode.
- `core/status_policy.py` — statuses, thresholds, texts for UI and API.
- `core/error_messages.py` — unified error texts for report, windows and API.
- `notifiers/notification_client.py`, `notifiers/notify.py` — HTTP API.
- `notifiers/windows_notifier.py` — Windows notifications.
- `config/settings.py`, `config/env_parsers.py` — configuration.

## Docker on Linux

Instructions in this section are intended **only for Linux host** with [Docker Engine](https://docs.docker.com/engine/install/) and [Compose](https://docs.docker.com/compose/install/linux/) plugin installed. Docker Desktop on Windows or macOS is **not** covered here: paths, socket permissions and examples are oriented to a regular Linux Docker daemon.

### Preparation

```bash
cd /path/to/ssl_checker
cp .env.example .env
# edit .env
```

Files in repository: `Dockerfile`, `docker-compose.yml`. In compose, `./.env` → `/app/.env` (read-only) and `./logs` → `/app/logs` are mounted.

In `docker-compose.yml`, **`RUN_BATCH_ON_START=true`** runs a batch when the container starts; further runs follow **`DAILY_BATCH_HOURS`** from `.env` (at :00 each hour, `SCHEDULER_TIMEZONE`). To skip the startup batch, set `RUN_BATCH_ON_START=false` in compose or `.env` (compose `environment` overrides `.env`).

### Default Service (Scheduler)

The default image runs `python main.py --schedule` — daily batch check at time from `.env`.

```bash
docker compose up -d --build
```

### One-time CLI (Separate Container)

Without stopping the `--schedule` service, you can run the utility in a single ephemeral container:

```bash
docker compose run --rm ssl-checker ssl-checker --help
docker compose run --rm ssl-checker ssl-checker --site example.com --json
docker compose run --rm ssl-checker ssl-checker --batch
docker compose run --rm ssl-checker ssl-checker --batch --notify-always
```

### CLI in Already Running Container

```bash
docker compose exec ssl-checker ssl-checker --site example.com --json
```

### Environment Notes

- Windows window notifications on Linux container **are not** used; for alerts, set corporate HTTP API in `.env` (`SEND_NOTIFICATIONS` and related variables). API sending rules are the same as for **`--batch`**: only on **reasons** for hosts; the **`--notify-always`** flag in background **`--schedule`** does not apply.
- Scheduler timezone is set by `SCHEDULER_TIMEZONE` in `.env`; `tzdata` is installed in the image.
- Background service from compose runs a batch on start (`RUN_BATCH_ON_START=true` in compose) and then on cron at hours from `DAILY_BATCH_HOURS`.

## Useful uv Commands

```bash
uv add <package>
uv remove <package>
uv lock
uv sync
```