from pathlib import Path
import subprocess
import sys

import pandas as pd
import streamlit as st

from config_utils import load_config, add_ticker, remove_ticker
from db import (
    latest_with_changes,
    with_changes,
    load_all,
    latest_daily_changes,
)
from exporter import export_excel


st.set_page_config(
    page_title="Options Flow Tracker",
    layout="wide",
)

st.title("Options Flow Tracker")

cfg = load_config()
db_path = cfg["database"]


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("Tracked Stocks")

    # --------------------------------------------------------
    # ADD TICKER — always visible
    # --------------------------------------------------------
    new_ticker = st.text_input(
        "Add a ticker",
        placeholder="e.g. TSLA, MSFT, META",
        key="sidebar_add_ticker",
    )

    if st.button(
        "➕ Add to Tracker",
        use_container_width=True,
    ):
        t = new_ticker.strip().upper().replace("US.", "")

        if not t:
            st.warning("Enter a ticker first.")
        else:
            before = set(load_config()["tickers"])
            add_ticker(t)
            after = set(load_config()["tickers"])

            if t in before:
                st.info(f"{t} is already in the tracker.")
            elif t in after:
                st.success(f"{t} added to the automatic tracker.")
                st.rerun()
            else:
                st.error(f"Could not add {t}.")

    # --------------------------------------------------------
    # REMOVE TICKER
    # --------------------------------------------------------
    current_tickers = load_config()["tickers"]

    if current_tickers:
        remove_choice = st.selectbox(
            "Remove a ticker",
            current_tickers,
            key="sidebar_remove_ticker",
        )

        if st.button(
            "➖ Remove from Tracker",
            use_container_width=True,
        ):
            remove_ticker(remove_choice)
            st.success(f"{remove_choice} removed.")
            st.rerun()

    st.divider()

    # --------------------------------------------------------
    # MANUAL COLLECTION
    # --------------------------------------------------------
    st.header("Manual Collection")

    current_tickers = load_config()["tickers"]

    selected = st.multiselect(
        "Stocks to collect now",
        current_tickers,
        default=current_tickers,
        key="manual_selected_tickers",
    )

    snap = st.selectbox(
        "Snapshot label",
        ["MANUAL", "PREMARKET", "EOD"],
        key="manual_snapshot_label",
    )

    if st.button(
        "▶ Run Selected Now",
        type="primary",
        use_container_width=True,
    ):
        if not selected:
            st.warning("Select at least one ticker.")
        else:
            with st.spinner("Collecting selected stocks..."):
                cmd = [
                    sys.executable,
                    "collector.py",
                    "--snapshot",
                    snap,
                    "--tickers",
                ] + selected

                proc = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                )

            if proc.returncode == 0:
                st.success("Collection completed.")
                st.code(proc.stdout or "Done")
                st.rerun()
            else:
                st.error("Collection failed.")
                st.code(
                    (proc.stdout or "")
                    + "\n"
                    + (proc.stderr or "")
                )

    st.divider()

    # --------------------------------------------------------
    # RUN ONE TICKER WITHOUT ADDING IT
    # --------------------------------------------------------
    st.subheader("Run One Ticker Once")

    run_once = st.text_input(
        "Ticker",
        placeholder="e.g. UBER",
        key="run_once_ticker",
    )

    if st.button(
        "Run Once",
        use_container_width=True,
    ):
        t = run_once.strip().upper().replace("US.", "")

        if not t:
            st.warning("Enter a ticker first.")
        else:
            with st.spinner(f"Collecting {t}..."):
                proc = subprocess.run(
                    [
                        sys.executable,
                        "collector.py",
                        "--snapshot",
                        "MANUAL",
                        "--tickers",
                        t,
                    ],
                    text=True,
                    capture_output=True,
                )

            if proc.returncode == 0:
                st.success(f"{t} collected.")
                st.code(proc.stdout or "Done")
                st.rerun()
            else:
                st.error("Collection failed.")
                st.code(
                    (proc.stdout or "")
                    + "\n"
                    + (proc.stderr or "")
                )

    st.divider()

    st.caption("Automatic schedule")
    st.write("08:00 / 08:30 / 09:00 / 09:20 ET — PREMARKET checks")
    st.write("16:20 ET — EOD")


# ============================================================
# MAIN TABS
# ============================================================
tab_daily, tab_live, tab_history, tab_manage = st.tabs(
    [
        "Daily Change",
        "Latest Flow",
        "Historical Data",
        "Tracked Stocks",
    ]
)


# ============================================================
# TRACKED STOCKS TAB
# ============================================================
with tab_manage:
    st.subheader("Tracked Stocks")

    current = load_config()["tickers"]

    st.write(
        "These tickers are included in the automatic scheduled collection."
    )

    st.dataframe(
        pd.DataFrame({"Ticker": current}),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Use the left sidebar to add or remove tickers."
    )


# ============================================================
# DATABASE CHECK
# ============================================================
if not Path(db_path).exists():
    with tab_daily:
        st.info("No database yet. Collect your first snapshot.")
    with tab_live:
        st.info("No database yet. Collect your first snapshot.")
    with tab_history:
        st.info("Historical data will appear after the first collection.")

    st.stop()


latest = latest_with_changes(db_path)
all_changes = with_changes(db_path)
all_raw = load_all(db_path)


# ============================================================
# DAILY CHANGE
# ============================================================
with tab_daily:
    daily = latest_daily_changes(db_path)

    if daily.empty:
        st.warning(
            "No strict Daily Change yet. "
            "At least two PREMARKET_CONFIRMED snapshots "
            "for the same contract are required."
        )
    else:
        ticker = st.selectbox(
            "Ticker",
            sorted(daily["ticker"].dropna().unique()),
            key="daily_ticker",
        )

        t = daily[
            daily["ticker"] == ticker
        ].copy()

        expiries = (
            ["All"]
            + sorted(
                t["expiration"]
                .dropna()
                .unique()
                .tolist()
            )
        )

        exp = st.selectbox(
            "Expiration",
            expiries,
            key="daily_expiration",
        )

        if exp != "All":
            t = t[
                t["expiration"] == exp
            ]

        call_change = pd.to_numeric(
            t.loc[
                t["option_type"] == "CALL",
                "daily_delta_oi",
            ],
            errors="coerce",
        ).sum()

        put_change = pd.to_numeric(
            t.loc[
                t["option_type"] == "PUT",
                "daily_delta_oi",
            ],
            errors="coerce",
        ).sum()

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Call Daily ΔOI",
            f"{call_change:,.0f}",
        )

        c2.metric(
            "Put Daily ΔOI",
            f"{put_change:,.0f}",
        )

        c3.metric(
            "Call - Put ΔOI",
            f"{call_change - put_change:,.0f}",
        )

        c4.metric(
            "Comparable contracts",
            f"{t['daily_delta_oi'].notna().sum():,}",
        )

        display = t[
            [
                "capture_date",
                "expiration",
                "strike",
                "option_type",
                "prev_oi",
                "open_interest",
                "daily_delta_oi",
                "daily_delta_oi_pct",
                "prev_day_volume",
                "delta_oi_to_prev_volume",
                "prev_premarket_date",
                "prev_eod_date",
            ]
        ].copy()

        display["daily_delta_oi_pct"] = (
            pd.to_numeric(
                display["daily_delta_oi_pct"],
                errors="coerce",
            )
            * 100
        ).round(1)

        display["delta_oi_to_prev_volume"] = (
            pd.to_numeric(
                display["delta_oi_to_prev_volume"],
                errors="coerce",
            )
            * 100
        ).round(1)

        display = display.rename(
            columns={
                "capture_date": "Today",
                "expiration": "Expiration",
                "strike": "Strike",
                "option_type": "Type",
                "prev_oi": "Previous OI",
                "open_interest": "Today OI",
                "daily_delta_oi": "Daily ΔOI",
                "daily_delta_oi_pct": "Daily ΔOI %",
                "prev_day_volume": "Previous Day Volume",
                "delta_oi_to_prev_volume": "ΔOI / Prev Volume %",
                "prev_premarket_date": "Previous Premarket Date",
                "prev_eod_date": "Previous EOD Date",
            }
        )

        st.subheader(
            f"{ticker} — Daily OI Change"
        )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader(
            "Largest Daily OI Builds"
        )

        rank = (
            t.dropna(
                subset=["daily_delta_oi"]
            )
            .sort_values(
                "daily_delta_oi",
                ascending=False,
            )
            .head(15)
        )

        st.dataframe(
            rank[
                [
                    "expiration",
                    "strike",
                    "option_type",
                    "prev_oi",
                    "open_interest",
                    "daily_delta_oi",
                    "prev_day_volume",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# LATEST FLOW
# ============================================================
with tab_live:
    if latest.empty:
        st.info("No snapshots yet.")
    else:
        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Tracked tickers",
            latest["ticker"].nunique(),
        )

        c2.metric(
            "Current contracts",
            len(latest),
        )

        c3.metric(
            "Latest capture",
            pd.to_datetime(
                latest["captured_at"]
            )
            .max()
            .strftime("%Y-%m-%d %H:%M"),
        )

        c4.metric(
            "Total snapshots",
            all_raw["captured_at"].nunique(),
        )

        ticker = st.selectbox(
            "Ticker",
            sorted(
                latest["ticker"].unique()
            ),
            key="latest_ticker",
        )

        t = latest[
            latest["ticker"] == ticker
        ].copy()

        expiries = sorted(
            t["expiration"]
            .dropna()
            .unique()
        )

        expiry = st.selectbox(
            "Expiration",
            ["All"] + expiries,
            key="latest_expiration",
        )

        if expiry != "All":
            t = t[
                t["expiration"] == expiry
            ]

        display = t[
            [
                "expiration",
                "strike",
                "option_type",
                "spot",
                "option_volume",
                "open_interest",
                "delta_oi",
                "delta_oi_pct",
                "vol_oi",
                "implied_volatility",
                "option_close",
                "snapshot_type",
                "captured_at",
            ]
        ].copy()

        display["delta_oi_pct"] = (
            pd.to_numeric(
                display["delta_oi_pct"],
                errors="coerce",
            )
            * 100
        ).round(1)

        display["vol_oi"] = pd.to_numeric(
            display["vol_oi"],
            errors="coerce",
        ).round(2)

        st.subheader(
            f"{ticker} — Latest Flow"
        )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader(
            "Largest OI Builds"
        )

        rank = (
            t.dropna(
                subset=["delta_oi"]
            )
            .sort_values(
                "delta_oi",
                ascending=False,
            )
            .head(15)
        )

        st.dataframe(
            rank[
                [
                    "expiration",
                    "strike",
                    "option_type",
                    "option_volume",
                    "open_interest",
                    "delta_oi",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# HISTORICAL DATA
# ============================================================
with tab_history:
    if all_changes.empty:
        st.info("No historical data.")
    else:
        h = all_changes.copy()

        h["captured_at"] = pd.to_datetime(
            h["captured_at"],
            errors="coerce",
        )

        c1, c2, c3, c4 = st.columns(4)

        ticker_f = c1.selectbox(
            "Ticker",
            ["All"]
            + sorted(
                h["ticker"]
                .dropna()
                .unique()
                .tolist()
            ),
            key="hist_ticker",
        )

        snap_f = c2.selectbox(
            "Snapshot",
            ["All"]
            + sorted(
                h["snapshot_type"]
                .dropna()
                .unique()
                .tolist()
            ),
            key="hist_snapshot",
        )

        opt_f = c3.selectbox(
            "Type",
            ["All", "CALL", "PUT"],
            key="hist_type",
        )

        dates = sorted(
            h["captured_at"]
            .dt.date
            .dropna()
            .unique()
        )

        date_f = c4.selectbox(
            "Date",
            ["All"]
            + [
                str(d)
                for d in dates
            ],
            key="hist_date",
        )

        if ticker_f != "All":
            h = h[
                h["ticker"] == ticker_f
            ]

        if snap_f != "All":
            h = h[
                h["snapshot_type"] == snap_f
            ]

        if opt_f != "All":
            h = h[
                h["option_type"] == opt_f
            ]

        if date_f != "All":
            h = h[
                h["captured_at"]
                .dt.date
                .astype(str)
                == date_f
            ]

        exps = (
            ["All"]
            + sorted(
                h["expiration"]
                .dropna()
                .unique()
                .tolist()
            )
        )

        exp_f = st.selectbox(
            "Expiration filter",
            exps,
            key="hist_expiration",
        )

        if exp_f != "All":
            h = h[
                h["expiration"] == exp_f
            ]

        st.dataframe(
            h.sort_values(
                "captured_at",
                ascending=False,
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Export")

        export_date = (
            None
            if date_f == "All"
            else date_f
        )

        if st.button(
            "Export Current Date to Excel"
        ):
            try:
                path = export_excel(
                    db_path,
                    date_filter=export_date,
                )

                data = Path(
                    path
                ).read_bytes()

                st.download_button(
                    "Download Excel",
                    data=data,
                    file_name=Path(path).name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )

            except Exception as e:
                st.error(str(e))
