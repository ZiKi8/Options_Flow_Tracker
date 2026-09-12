# Options Flow Tracker v2

## What changed in v2

- Add/remove tracked stocks directly from the Dashboard.
- Select any subset of tracked stocks and click **Run Selected Now**.
- Enter an untracked ticker and click **Run Once**.
- Historical Data page with filters for ticker, date, snapshot type, option type and expiration.
- Export selected date to Excel from the Dashboard.
- Automatic EOD Excel export.
- Automatic Friday EOD database backup.
- Scheduled 08:00 ET and 16:20 ET collections remain supported.

## Tracking rule

For every selected stock:

- Underlying spot ± $10
- Strike must be a multiple of $5
- Nearest 2 available expirations
- Plus nearest available standard expiration in Mar/Jun/Sep/Dec
- CALL and PUT
- Store volume, open interest, IV, option close and spot
- Calculate ΔOI from the prior stored observation of the same contract

## Storage

The main database is:

`options_flow.db`

It is never replaced during normal collection. New snapshots are appended.

EOD exports go to:

`exports/YYYY-MM-DD_options_flow.xlsx`

Friday EOD backups go to:

`backups/options_flow_YYYY-MM-DD_HHMM.db`

## First-time setup

```bash
pip install -r requirements.txt
python auth_setup.py
```

Then launch:

```bash
streamlit run app.py
```

or double-click `start_dashboard.bat`.

## Dashboard workflow

### Tracked Stocks
Add/remove stocks that should be collected automatically.

### Latest Flow
View the latest stored option-flow snapshot and the largest ΔOI builds.

### Historical Data
Filter the database without opening SQLite manually.

### Manual collection
Use the sidebar:

- **Run Selected Now** — collect selected watchlist stocks immediately.
- **Run Once** — temporarily collect one ticker without adding it to the watchlist.

## Automatic schedule

In PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_tasks.ps1
```

Creates:

- Mon–Fri 08:00 ET PREMARKET
- Mon–Fri 16:20 ET EOD

## Important

Your PC must be awake and connected to the internet for Windows Task Scheduler to run the collection. For true unattended collection while the PC is off, the collector would need to run on an always-on machine or cloud service.
