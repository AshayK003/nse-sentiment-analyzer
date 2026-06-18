"""Market-wide data for NSE Sentiment Analyzer.
FII/DII institutional flow fetched via nsepython.
"""

import streamlit as st
import pandas as pd


@st.cache_data(ttl=3600)
def get_fii_dii_flow():
    """Fetch latest FII/DII net flow from NSE India.

    Returns a dict:
        {
            "fii_net": float (Cr),
            "dii_net": float (Cr),
            "date": str,
            "combined_net": float (Cr),
            "fii_action": "Buying"|"Selling"|"Flat",
            "dii_action": "Buying"|"Selling"|"Flat",
        }
    Returns None on failure.
    """
    try:
        from nsepython import nse_fiidii
        df = nse_fiidii()
        if df is None or df.empty:
            return None

        fii_row = df[df["category"].str.contains("FII|FPI", case=False, na=False)]
        dii_row = df[df["category"].str.contains("DII", case=False, na=False)]

        fii_net = float(fii_row["netValue"].iloc[0]) if not fii_row.empty else 0.0
        dii_net = float(dii_row["netValue"].iloc[0]) if not dii_row.empty else 0.0
        date = str(fii_row["date"].iloc[0]) if not fii_row.empty else str(dii_row["date"].iloc[0]) if not dii_row.empty else ""

        def action(net):
            if net > 200:
                return "Buying"
            elif net < -200:
                return "Selling"
            else:
                return "Flat"

        return {
            "fii_net": fii_net,
            "dii_net": dii_net,
            "date": date,
            "combined_net": fii_net + dii_net,
            "fii_action": action(fii_net),
            "dii_action": action(dii_net),
        }
    except Exception:
        return None
