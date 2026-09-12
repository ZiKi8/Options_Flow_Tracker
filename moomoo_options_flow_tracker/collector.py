import argparse
import math
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config_utils import load_config, normalize_ticker
from moomoo_rest import MoomooREST
from db import insert_rows
from exporter import export_excel
from backup import backup_database


def nearest_step_strikes(spot, radius, step):
    low = spot - radius
    high = spot + radius

    first = math.ceil(low / step) * step

    values = []
    x = first

    while x <= high + 1e-9:
        values.append(float(x))
        x += step

    return values


def is_quarterly(exp_date):
    """
    Operational quarterly rule:
    nearest available expiration in Mar / Jun / Sep / Dec.
    """
    return exp_date.month in (3, 6, 9, 12)


def choose_expirations(chain, weekly_count=2, include_quarterly=True):
    dates = sorted({
        c.get("strike_time")
        for c in chain
        if c.get("strike_time")
    })

    parsed = [
        (d, datetime.strptime(d, "%Y-%m-%d").date())
        for d in dates
    ]

    today = date.today()

    future = [
        (s, d)
        for s, d in parsed
        if d >= today
    ]

    chosen = [
        s
        for s, _ in future[:weekly_count]
    ]

    if include_quarterly:
        quarterly = next(
            (
                s
                for s, d in future
                if is_quarterly(d) and s not in chosen
            ),
            None,
        )

        if quarterly:
            chosen.append(quarterly)

    return chosen


def latest_daily_bar(api, symbol):
    today = date.today()

    start = (today - timedelta(days=14)).isoformat()
    end = today.isoformat()

    bars = api.history_kline(
        symbol,
        start,
        end,
        num=20,
    )

    if not bars:
        return None

    return bars[-1]


def today_already_confirmed(db_path, ticker):
    """
    True if today's PREMARKET_CONFIRMED snapshot already exists
    for this ticker.
    """
    if not Path(db_path).exists():
        return False

    con = sqlite3.connect(db_path)

    try:
        query = """
        SELECT COUNT(*)
        FROM snapshots
        WHERE ticker = ?
          AND snapshot_type = 'PREMARKET_CONFIRMED'
          AND date(captured_at) = date('now', 'localtime')
        """

        count = con.execute(
            query,
            (ticker,),
        ).fetchone()[0]

        return count > 0

    finally:
        con.close()


def previous_confirmed_oi(db_path, ticker):
    """
    Return previous confirmed premarket OI:
        {option_code: open_interest}

    Uses the most recent date before today that contains
    PREMARKET_CONFIRMED for this ticker.
    """
    if not Path(db_path).exists():
        return {}

    con = sqlite3.connect(db_path)

    try:
        query = """
        SELECT option_code, open_interest
        FROM snapshots
        WHERE ticker = ?
          AND snapshot_type = 'PREMARKET_CONFIRMED'
          AND date(captured_at) = (
              SELECT MAX(date(captured_at))
              FROM snapshots
              WHERE ticker = ?
                AND snapshot_type = 'PREMARKET_CONFIRMED'
                AND date(captured_at) < date('now', 'localtime')
          )
        """

        df = pd.read_sql_query(
            query,
            con,
            params=(ticker, ticker),
        )

    finally:
        con.close()

    if df.empty:
        return {}

    df["open_interest"] = pd.to_numeric(
        df["open_interest"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["option_code", "open_interest"]
    )

    return dict(
        zip(
            df["option_code"],
            df["open_interest"],
        )
    )


def confirm_premarket_update(
    db_path,
    ticker,
    ticker_rows,
    minimum_change_ratio=0.10,
):
    """
    Decide whether current PREMARKET OI appears refreshed.

    Returns:
        "ALREADY_CONFIRMED"
        "BASELINE"
        "CONFIRMED"
        "NOT_UPDATED"
        "NO_COMPARABLE"

    Rule:
    - first-ever confirmed observation becomes baseline;
    - otherwise at least 10% of comparable contracts must have
      changed OI versus previous confirmed day.
    """

    if today_already_confirmed(
        db_path,
        ticker,
    ):
        return "ALREADY_CONFIRMED"

    previous_oi = previous_confirmed_oi(
        db_path,
        ticker,
    )

    # First day: establish baseline.
    if not previous_oi:
        return "BASELINE"

    changed = 0
    comparable = 0

    for row in ticker_rows:
        code = row.get("option_code")

        if code not in previous_oi:
            continue

        old_oi = previous_oi.get(code)
        new_oi = row.get("open_interest")

        if (
            old_oi is None
            or new_oi is None
            or pd.isna(old_oi)
            or pd.isna(new_oi)
        ):
            continue

        try:
            old_oi = float(old_oi)
            new_oi = float(new_oi)
        except (TypeError, ValueError):
            continue

        comparable += 1

        if new_oi != old_oi:
            changed += 1

    if comparable == 0:
        print(
            f"{ticker}: no comparable contracts "
            "with the previous confirmed snapshot."
        )
        return "NO_COMPARABLE"

    change_ratio = changed / comparable

    print(
        f"{ticker}: OI changed in "
        f"{changed}/{comparable} comparable contracts "
        f"({change_ratio:.1%})."
    )

    if change_ratio >= minimum_change_ratio:
        return "CONFIRMED"

    return "NOT_UPDATED"


def collect(
    snapshot_type="MANUAL",
    tickers=None,
):
    cfg = load_config()

    tz = ZoneInfo(
        cfg.get(
            "timezone",
            "America/New_York",
        )
    )

    captured_at = datetime.now(
        tz
    ).isoformat(
        timespec="seconds"
    )

    api = MoomooREST()

    target_tickers = [
        normalize_ticker(x)
        for x in (
            tickers
            or cfg["tickers"]
        )
    ]

    target_tickers = [
        x
        for x in target_tickers
        if x
    ]

    total_collected = 0

    for ticker in target_tickers:

        # If today's premarket OI has already been confirmed,
        # skip immediately before making unnecessary option requests.
        if (
            snapshot_type == "PREMARKET"
            and today_already_confirmed(
                cfg["database"],
                ticker,
            )
        ):
            print(
                f"{ticker}: today's PREMARKET_CONFIRMED "
                "already exists. Skip."
            )
            continue

        try:
            stock_bar = latest_daily_bar(
                api,
                f"US.{ticker}",
            )
        except Exception as e:
            print(
                f"[WARN] failed to get stock data "
                f"for {ticker}: {e}"
            )
            continue

        if not stock_bar:
            print(
                f"[WARN] no stock data for {ticker}"
            )
            continue

        try:
            spot = float(
                stock_bar.get("close")
                or 0
            )
        except (TypeError, ValueError):
            spot = 0

        if spot <= 0:
            print(
                f"[WARN] invalid spot for {ticker}: "
                f"{stock_bar.get('close')}"
            )
            continue

        try:
            chain = api.option_chain(
                ticker,
                date.today().isoformat(),
                (
                    date.today()
                    + timedelta(days=120)
                ).isoformat(),
            )
        except Exception as e:
            print(
                f"[WARN] failed option chain "
                f"for {ticker}: {e}"
            )
            continue

        if not chain:
            print(
                f"[WARN] no option chain for {ticker}"
            )
            continue

        target_expirations = set(
            choose_expirations(
                chain,
                cfg.get(
                    "weekly_expirations",
                    2,
                ),
                cfg.get(
                    "include_quarterly",
                    True,
                ),
            )
        )

        allowed_strikes = set(
            nearest_step_strikes(
                spot,
                cfg.get(
                    "spot_range_dollars",
                    10,
                ),
                cfg.get(
                    "strike_step",
                    5,
                ),
            )
        )

        selected = []

        for contract in chain:
            try:
                strike = float(
                    contract.get(
                        "strike_price"
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                contract.get("strike_time")
                not in target_expirations
            ):
                continue

            if strike not in allowed_strikes:
                continue

            if (
                contract.get("option_type")
                not in ("CALL", "PUT")
            ):
                continue

            selected.append(contract)

        print(
            f"{ticker}: spot={spot:.2f}, "
            f"contracts={len(selected)}, "
            f"expiries={sorted(target_expirations)}"
        )

        ticker_rows = []

        for idx, contract in enumerate(
            selected,
            start=1,
        ):
            code = contract["code"]

            print(
                f"  [{idx}/{len(selected)}] "
                f"{code}"
            )

            try:
                bar = latest_daily_bar(
                    api,
                    code,
                )
            except Exception as e:
                print(
                    f"  [WARN] failed {code}: {e}"
                )
                continue

            if not bar:
                print(
                    f"  [WARN] no daily bar "
                    f"for {code}"
                )
                continue

            ticker_rows.append({
                "captured_at":
                    captured_at,

                "snapshot_type":
                    snapshot_type,

                "ticker":
                    ticker,

                "spot":
                    spot,

                "expiration":
                    contract["strike_time"],

                "strike":
                    float(
                        contract[
                            "strike_price"
                        ]
                    ),

                "option_type":
                    contract[
                        "option_type"
                    ],

                "option_code":
                    code,

                "option_close":
                    bar.get("close"),

                "option_volume":
                    bar.get("volume"),

                "open_interest":
                    bar.get(
                        "open_interest"
                    ),

                "implied_volatility":
                    bar.get(
                        "implied_volatility"
                    ),

                "source_trade_date":
                    str(
                        bar.get(
                            "date",
                            "",
                        )
                    ),
            })

        if not ticker_rows:
            print(
                f"{ticker}: no usable contracts collected."
            )
            continue

        # ==========================================================
        # PREMARKET confirmation logic
        # ==========================================================
        if snapshot_type == "PREMARKET":

            status = confirm_premarket_update(
                cfg["database"],
                ticker,
                ticker_rows,
                minimum_change_ratio=0.10,
            )

            if status == "ALREADY_CONFIRMED":
                print(
                    f"{ticker}: already confirmed today. "
                    "Nothing saved."
                )
                continue

            if status == "BASELINE":
                print(
                    f"{ticker}: no previous confirmed OI. "
                    "Saving today's data as initial baseline."
                )

                for row in ticker_rows:
                    row["snapshot_type"] = (
                        "PREMARKET_CONFIRMED"
                    )

                saved = insert_rows(
                    cfg["database"],
                    ticker_rows,
                )

                total_collected += saved

                print(
                    f"{ticker}: initial "
                    f"PREMARKET_CONFIRMED saved "
                    f"({saved} rows)."
                )

                continue

            if status == "CONFIRMED":
                print(
                    f"{ticker}: OI UPDATE DETECTED."
                )

                for row in ticker_rows:
                    row["snapshot_type"] = (
                        "PREMARKET_CONFIRMED"
                    )

                saved = insert_rows(
                    cfg["database"],
                    ticker_rows,
                )

                total_collected += saved

                print(
                    f"{ticker}: confirmed premarket "
                    f"snapshot saved "
                    f"({saved} rows)."
                )

                continue

            if status in (
                "NOT_UPDATED",
                "NO_COMPARABLE",
            ):
                print(
                    f"{ticker}: OI has NOT been "
                    "confirmed as updated yet. "
                    "Nothing saved. Check again later."
                )
                continue

        # ==========================================================
        # MANUAL / EOD normal save
        # ==========================================================
        saved = insert_rows(
            cfg["database"],
            ticker_rows,
        )

        total_collected += saved

        print(
            f"{ticker}: saved {saved} rows "
            f"as {snapshot_type}."
        )

    print(
        f"Completed snapshot. "
        f"Saved {total_collected} rows "
        f"at {captured_at}."
    )

    # ==============================================================
    # Existing EOD export + Friday backup
    # ==============================================================
    if (
        snapshot_type == "EOD"
        and cfg.get(
            "auto_export_eod",
            True,
        )
    ):
        try:
            path = export_excel(
                cfg["database"],
                date_filter=(
                    date.today().isoformat()
                ),
            )

            print(
                f"Excel exported: {path}"
            )

        except Exception as e:
            print(
                f"[WARN] export failed: {e}"
            )

    if (
        snapshot_type == "EOD"
        and date.today().weekday() == 4
        and cfg.get(
            "backup_on_friday_eod",
            True,
        )
    ):
        try:
            path = backup_database(
                cfg["database"]
            )

            print(
                f"Database backup: {path}"
            )

        except Exception as e:
            print(
                f"[WARN] backup failed: {e}"
            )

    return total_collected


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--snapshot",
        default="MANUAL",
        choices=[
            "PREMARKET",
            "EOD",
            "MANUAL",
        ],
    )

    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
    )

    args = parser.parse_args()

    collect(
        args.snapshot,
        args.tickers,
    )
