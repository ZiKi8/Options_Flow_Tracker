import sqlite3
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    snapshot_type TEXT NOT NULL,
    ticker TEXT NOT NULL,
    spot REAL,
    expiration TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL,
    option_code TEXT NOT NULL,
    option_close REAL,
    option_volume REAL,
    open_interest REAL,
    implied_volatility REAL,
    source_trade_date TEXT,
    UNIQUE(captured_at, snapshot_type, option_code)
);
CREATE INDEX IF NOT EXISTS idx_contract ON snapshots(option_code, captured_at);
CREATE INDEX IF NOT EXISTS idx_ticker ON snapshots(ticker, captured_at);
"""

def connect(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con

def insert_rows(path, rows):
    if not rows:
        return 0
    con = connect(path)
    sql = """
    INSERT OR IGNORE INTO snapshots (
        captured_at,snapshot_type,ticker,spot,expiration,strike,option_type,
        option_code,option_close,option_volume,open_interest,implied_volatility,
        source_trade_date
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    vals = [(
        r["captured_at"], r["snapshot_type"], r["ticker"], r.get("spot"),
        r["expiration"], r["strike"], r["option_type"], r["option_code"],
        r.get("option_close"), r.get("option_volume"), r.get("open_interest"),
        r.get("implied_volatility"), r.get("source_trade_date"),
    ) for r in rows]
    con.executemany(sql, vals)
    con.commit()
    n = con.total_changes
    con.close()
    return n

def load_all(path):
    con = connect(path)
    df = pd.read_sql_query(
        "SELECT * FROM snapshots ORDER BY captured_at DESC, ticker, expiration, strike, option_type",
        con
    )
    con.close()
    return df

# Existing snapshot-to-snapshot analytics for Latest Flow
def with_changes(path):
    df = load_all(path)
    if df.empty:
        return df

    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df["option_volume"] = pd.to_numeric(df["option_volume"], errors="coerce")

    df = df.sort_values(["option_code", "captured_at"])
    df["prev_oi"] = df.groupby("option_code")["open_interest"].shift(1)
    df["delta_oi"] = df["open_interest"] - df["prev_oi"]
    df["delta_oi_pct"] = df["delta_oi"] / df["prev_oi"].replace(0, pd.NA)
    df["vol_oi"] = df["option_volume"] / df["open_interest"].replace(0, pd.NA)
    return df

def latest_with_changes(path):
    df = with_changes(path)
    if df.empty:
        return df
    return (
        df.groupby("option_code", as_index=False)
          .tail(1)
          .sort_values(["ticker", "expiration", "strike", "option_type"])
    )

# Strict daily analytics based ONLY on confirmed premarket OI
def daily_changes(path):
    """
    Daily ΔOI =
        today's PREMARKET_CONFIRMED OI
        - previous PREMARKET_CONFIRMED OI

    Previous-day Volume =
        most recent EOD volume before today's confirmed premarket date.

    MANUAL and unconfirmed PREMARKET observations do not affect Daily ΔOI.
    """
    df = load_all(path)
    if df.empty:
        return pd.DataFrame()

    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
    df["capture_date"] = df["captured_at"].dt.date
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df["option_volume"] = pd.to_numeric(df["option_volume"], errors="coerce")
    df["implied_volatility"] = pd.to_numeric(df["implied_volatility"], errors="coerce")
    df["option_close"] = pd.to_numeric(df["option_close"], errors="coerce")

    pre = df[df["snapshot_type"] == "PREMARKET_CONFIRMED"].copy()
    if pre.empty:
        return pd.DataFrame()

    # Keep the last confirmed observation for each contract/date.
    pre = (
        pre.sort_values("captured_at")
           .groupby(["option_code", "capture_date"], as_index=False)
           .tail(1)
           .sort_values(["option_code", "captured_at"])
    )

    pre["prev_premarket_date"] = pre.groupby("option_code")["capture_date"].shift(1)
    pre["prev_oi"] = pre.groupby("option_code")["open_interest"].shift(1)
    pre["daily_delta_oi"] = pre["open_interest"] - pre["prev_oi"]
    pre["daily_delta_oi_pct"] = (
        pre["daily_delta_oi"] / pre["prev_oi"].replace(0, pd.NA)
    )

    # Match the most recent EOD snapshot strictly before today's confirmed date.
    eod = df[df["snapshot_type"] == "EOD"].copy()
    eod_map = {}

    if not eod.empty:
        eod = (
            eod.sort_values("captured_at")
               .groupby(["option_code", "capture_date"], as_index=False)
               .tail(1)
        )
        for code, g in eod.groupby("option_code"):
            eod_map[code] = g.sort_values("capture_date")

    prev_volumes = []
    prev_eod_dates = []
    prev_eod_closes = []
    prev_eod_ivs = []

    for row in pre.itertuples(index=False):
        g = eod_map.get(row.option_code)

        if g is None or g.empty:
            prev_volumes.append(pd.NA)
            prev_eod_dates.append(pd.NaT)
            prev_eod_closes.append(pd.NA)
            prev_eod_ivs.append(pd.NA)
            continue

        candidates = g[g["capture_date"] < row.capture_date]

        if candidates.empty:
            prev_volumes.append(pd.NA)
            prev_eod_dates.append(pd.NaT)
            prev_eod_closes.append(pd.NA)
            prev_eod_ivs.append(pd.NA)
            continue

        last = candidates.iloc[-1]
        prev_volumes.append(last["option_volume"])
        prev_eod_dates.append(last["capture_date"])
        prev_eod_closes.append(last["option_close"])
        prev_eod_ivs.append(last["implied_volatility"])

    pre["prev_day_volume"] = prev_volumes
    pre["prev_eod_date"] = prev_eod_dates
    pre["prev_eod_option_close"] = prev_eod_closes
    pre["prev_eod_iv"] = prev_eod_ivs

    pre["delta_oi_to_prev_volume"] = (
        pre["daily_delta_oi"]
        / pd.to_numeric(pre["prev_day_volume"], errors="coerce").replace(0, pd.NA)
    )

    return pre.sort_values(
        ["capture_date", "ticker", "expiration", "strike", "option_type"],
        ascending=[False, True, True, True, True]
    )

def latest_daily_changes(path):
    d = daily_changes(path)
    if d.empty:
        return d
    latest_date = d["capture_date"].max()
    return d[d["capture_date"] == latest_date].copy()
