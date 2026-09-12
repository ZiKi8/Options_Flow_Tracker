from pathlib import Path
from datetime import datetime
import pandas as pd
from db import with_changes

def export_excel(db_path, out_path=None, date_filter=None):
    df = with_changes(db_path)
    if df.empty:
        raise RuntimeError("No data to export.")

    if date_filter:
        d = pd.to_datetime(date_filter).date()
        df = df[pd.to_datetime(df["captured_at"]).dt.date == d]

    if df.empty:
        raise RuntimeError("No rows for selected date.")

    out_dir = Path("exports")
    out_dir.mkdir(exist_ok=True)
    if out_path is None:
        stamp = pd.to_datetime(df["captured_at"]).max().strftime("%Y-%m-%d")
        out_path = out_dir / f"{stamp}_options_flow.xlsx"
    else:
        out_path = Path(out_path)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary = (
            df.groupby(["ticker","snapshot_type"], dropna=False)
              .agg(
                  contracts=("option_code","count"),
                  total_volume=("option_volume","sum"),
                  total_oi=("open_interest","sum"),
                  total_delta_oi=("delta_oi","sum"),
              )
              .reset_index()
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)

        for ticker in sorted(df["ticker"].dropna().unique()):
            t = df[df["ticker"] == ticker].copy()
            t.to_excel(writer, sheet_name=str(ticker)[:31], index=False)

    return str(out_path)
