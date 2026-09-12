# Options Flow Tracker

A lightweight options-flow analytics tool built with Python and Streamlit.

This project collects selected U.S. equity option-chain snapshots and tracks key option metrics such as Open Interest (OI), volume, implied volatility, and option prices. It also provides a dashboard for reviewing daily OI changes and recent option-flow activity.

## Features

- Track selected U.S. stock tickers
- Monitor option contracts within a configurable price range around the underlying stock price
- Track Calls and Puts
- Collect Open Interest, volume, implied volatility, and option prices
- Compare daily Open Interest changes
- Match daily OI changes with previous-day option volume
- Identify the largest OI increases
- Review historical snapshots
- Add or remove tracked tickers from the dashboard
- Run manual data collection for selected tickers
- Export data to Excel
- Store historical snapshots in SQLite
- Automatically retry Moomoo REST API requests when rate limits are encountered

## Daily OI Update Logic

Open Interest data may update at different times during the pre-market session.

The tracker can check for OI updates at multiple times:

- 8:00 AM ET
- 8:30 AM ET
- 9:00 AM ET
- 9:20 AM ET

The program compares the current option OI values with the previous confirmed pre-market snapshot. Once enough comparable contracts show updated OI values, the snapshot is saved as:

```text
PREMARKET_CONFIRMED
```

Daily OI change is calculated as:

```text
Daily ΔOI = Today's Confirmed OI - Previous Confirmed OI
```

The end-of-day snapshot is scheduled for:

```text
4:20 PM ET
```

This snapshot is used to preserve end-of-day option volume and related metrics.

## Dashboard

The Streamlit dashboard includes:

### Daily Change

Displays:

- Previous OI
- Current OI
- Daily ΔOI
- Daily ΔOI %
- Previous-day volume
- ΔOI / previous-day volume
- Previous confirmed pre-market date
- Previous EOD date

### Latest Flow

Displays the most recent option snapshot and snapshot-to-snapshot changes.

### Historical Data

Allows filtering by:

- Ticker
- Snapshot type
- Call / Put
- Date
- Expiration

Historical data can also be exported to Excel.

### Tracked Stocks

Tickers can be added or removed from the tracking list directly from the dashboard.

## Project Structure

```text
options-flow-tracker/
│
├── app.py
├── collector.py
├── db.py
├── moomoo_rest.py
├── config_utils.py
├── exporter.py
├── backup.py
├── auth_setup.py
├── config.json
├── requirements.txt
├── install_tasks.ps1
└── README.md
```

Local runtime files such as OAuth tokens and SQLite databases should not be committed to GitHub.

## Installation

Create a clean Python environment before installing dependencies.

Example:

```bash
python -m venv app_env
```

Windows:

```powershell
.\app_env\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Moomoo API Authorization

This project uses the Moomoo REST API for market-data retrieval.

Complete the OAuth authorization process before running the collector:

```bash
python auth_setup.py
```

After successful authorization, the program may create local credential files such as:

```text
tokens.json
oauth_client.json
```

These files contain sensitive OAuth credentials and must not be committed to GitHub.

Recommended `.gitignore` entries:

```gitignore
tokens.json
oauth_client.json
.env
.streamlit/secrets.toml
*.db
__pycache__/
*.pyc
app_env/
build/
dist/
```

## Configuration

Tracked tickers and collection settings are stored in `config.json`.

Example:

```json
{
  "tickers": [
    "TSLA",
    "NVDA",
    "AAPL"
  ],
  "spot_range_dollars": 10,
  "strike_step": 5,
  "weekly_expirations": 2,
  "include_quarterly": true,
  "timezone": "America/New_York",
  "database": "options_flow.db"
}
```

Tracked tickers can also be changed from the Streamlit dashboard.

## Run the Dashboard

```bash
streamlit run app.py
```

or:

```bash
python -m streamlit run app.py
```

The dashboard normally opens at:

```text
http://localhost:8501
```

## Manual Collection

Collect all configured tickers:

```bash
python collector.py --snapshot MANUAL
```

Collect selected tickers:

```bash
python collector.py --snapshot MANUAL --tickers TSLA NVDA
```

Run a pre-market OI check:

```bash
python collector.py --snapshot PREMARKET
```

Run an end-of-day snapshot:

```bash
python collector.py --snapshot EOD
```

## Windows Scheduled Tasks

`install_tasks.ps1` can be used to configure automatic Windows Task Scheduler jobs.

The default schedule is:

```text
08:00 ET  PREMARKET
08:30 ET  PREMARKET
09:00 ET  PREMARKET
09:20 ET  PREMARKET
16:20 ET  EOD
```

Run the PowerShell installer from the project directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_tasks.ps1
```

## Data Storage

The local version uses SQLite:

```text
options_flow.db
```

The database stores historical option snapshots over time.

For cloud deployment or multi-user use, a persistent cloud database such as PostgreSQL is recommended instead of local SQLite.

## Security

Do not commit any API credentials, OAuth tokens, passwords, or secrets to GitHub.

In particular, do not upload:

```text
tokens.json
oauth_client.json
.env
.streamlit/secrets.toml
```

If a credential is accidentally committed to a public repository, revoke or regenerate it immediately.

## Deployment

The Streamlit dashboard can be deployed to Streamlit Community Cloud or another Python-compatible hosting platform.

For deployment:

- Store API credentials in environment variables or platform secrets
- Do not commit OAuth tokens
- Use persistent cloud storage for long-term historical data
- Restrict direct API-triggering controls when sharing the app with multiple users

## Disclaimer

This project is intended for research, educational, and analytical purposes.

It does not provide investment advice, trading recommendations, or guarantees regarding future market performance.

Market data availability, timing, and accuracy depend on the upstream data provider and the user's API permissions.

## License

A license has not yet been specified.
