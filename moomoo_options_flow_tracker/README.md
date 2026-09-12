# Options Flow Tracker


## Tracking rule

For every selected stock:

- Underlying spot ± $10
- Strike must be a multiple of $5
- Nearest 2 available expirations
- Plus nearest available standard expiration in Mar/Jun/Sep/Dec
- CALL and PUT
- Store volume, open interest, IV, option close and spot
- Calculate ΔOI from the prior stored observation of the same contract


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


