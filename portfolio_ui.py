"""Portfolio, track record, and institutional flow UI cards.

Extracted from app.py so the Streamlit orchestration layer stays focused
on layout and navigation (Issue #8).
"""
import re

import pandas as pd
import streamlit as st

from data_fetcher import resolve_ticker
from market_data import get_fii_dii_flow
from persistence import (
    ENTRY_PRICES_FILE,
    calc_portfolio_pnl,
    get_entry_info,
    history_to_csv,
    load_fiidii_history,
    load_sentiment_history,
    load_track_record,
    save_entry_price,
    save_fiidii_snapshot,
    save_portfolio,
)
from render import _is_valid_num


def render_bottom_cards(portfolio: list, final_ticker: str, entry_prices: dict) -> None:
    """Render the bottom Portfolio + Track Record cards section.

    Uses Streamlit native containers with glassmorphism styling for a
    premium look. Portfolio and Track Record sit side-by-side, with a
    sentiment history expander below.
    """
    _FOLDER = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    _BAR = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>'

    bc1, bc2 = st.columns([1.6, 1])
    eprices = entry_prices

    # ─── Portfolio Card ───
    with bc1:
        # Add ticker form (Streamlit widgets, outside card)
        ac1, ac2, ac3, ac4 = st.columns([1.8, 0.8, 0.8, 0.4])
        with ac1:
            new_t = st.text_input("Ticker", placeholder="RELIANCE", label_visibility="collapsed",
                                  max_chars=15, key="btm_add_ticker")
        with ac2:
            ep_input = st.text_input("ATP", placeholder="ATP", label_visibility="collapsed",
                                     max_chars=10, key="btm_add_atp",
                                     help="Average trade price for P&L tracking")
        with ac3:
            qty_input = st.text_input("Qty", placeholder="Qty", label_visibility="collapsed",
                                      max_chars=6, key="btm_add_qty",
                                      help="Number of shares held")
        with ac4:
            if st.button("+", use_container_width=True, key="btm_add_btn",
                         help="Add to portfolio") and new_t.strip():
                t = new_t.strip().upper().replace(".NS", "")
                # Resolve aliases (e.g. "HDFC BANK" → "HDFCBANK")
                _rt, _rn = resolve_ticker(t)
                if _rt:
                    t = _rt
                if not re.match(r'^[A-Z0-9&-]+$', t):
                    st.warning("Invalid ticker format")
                elif t in portfolio:
                    st.warning(f"{t} already in portfolio")
                else:
                    portfolio.append(t)
                    save_portfolio(portfolio)
                    qty_val = 1
                    if qty_input.strip():
                        try:
                            qty_val = int(qty_input.strip().replace(",", ""))
                        except ValueError:
                            pass
                    if ep_input.strip():
                        try:
                            save_entry_price(t, float(ep_input.strip().replace(",", "")), qty_val)
                        except ValueError:
                            st.warning("Could not parse ATP -- stock added without entry price")
                    else:
                        save_entry_price(t, 0, qty_val)
                    st.session_state._skip_reanalysis = True
                    st.rerun()

        # Portfolio rows (static HTML card)
        if portfolio:
            row_parts = []
            for t in portfolio:
                ep = eprices.get(t)
                sd = st.session_state.get("_stock_price_cache", {}).get(t)
                cp = sd.get("current_price") if sd else None

                ep_price, ep_qty = get_entry_info(ep)

                ticker_html = f'<span style="font-weight:600;font-size:0.85rem;color:#f0f2f5;min-width:3.5rem">{t}</span>'
                parts = [ticker_html]

                if _is_valid_num(cp):
                    parts.append(f'<span style="font-size:0.8rem;color:#c0c5ce">\u20b9{cp:,.2f}</span>')

                if ep_qty > 0:
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">\u00d7{ep_qty}</span>')

                if ep_price and _is_valid_num(cp):
                    pnl = calc_portfolio_pnl(ep_price, cp, ep_qty)
                    pnl_color = "#22c55e" if pnl["pnl_pct"] >= 0 else "#ef4444"
                    pnl_sign = "+" if pnl["pnl_pct"] >= 0 else ""
                    parts.append(f'<span style="font-size:0.78rem;font-weight:600;color:{pnl_color}">{pnl_sign}{pnl["pnl_pct"]:.1f}%</span>')
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">ATP \u20b9{ep_price:,.0f}</span>')
                elif ep_price:
                    parts.append(f'<span style="font-size:0.7rem;color:#6b7280">ATP \u20b9{ep_price:,.0f}</span>')

                row_parts.append(
                    f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0;'
                    f'border-bottom:1px solid rgba(42,46,58,0.4);line-height:1.3">'
                    f'{"".join(parts)}</div>'
                )

            # Summary stats (qty-weighted)
            total_invested = sum(
                get_entry_info(eprices.get(t))[0] * get_entry_info(eprices.get(t))[1]
                for t in portfolio if eprices.get(t)
            )
            total_current = sum(
                sd.get("current_price", 0) * get_entry_info(eprices.get(t))[1]
                for t in portfolio
                if (sd := st.session_state.get("_stock_price_cache", {}).get(t))
                and _is_valid_num(sd.get("current_price"))
            )
            n_with_prices = sum(
                1 for t in portfolio
                if st.session_state.get("_stock_price_cache", {}).get(t)
            )
            day_chg = sum(
                sd.get("change_pct", 0) or 0
                for t in portfolio
                if (sd := st.session_state.get("_stock_price_cache", {}).get(t))
            )
            day_avg = day_chg / n_with_prices if n_with_prices else 0
            total_pnl = total_current - total_invested if total_invested and total_current else None
            total_pnl_pct = (total_pnl / total_invested * 100) if total_pnl is not None else None

            sum_items = []
            if total_invested:
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Invested <span style="font-weight:600;color:#c0c5ce">\u20b9{total_invested:,.0f}</span></span>')
            if total_current:
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Current <span style="font-weight:600;color:#c0c5ce">\u20b9{total_current:,.0f}</span></span>')
            if total_pnl_pct is not None:
                pnl_color = "#22c55e" if total_pnl >= 0 else "#ef4444"
                pnl_sign = "+" if total_pnl >= 0 else ""
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">P&amp;L <span style="font-weight:600;color:{pnl_color}">{pnl_sign}{total_pnl_pct:.1f}%</span></span>')
            if day_avg:
                day_color = "#22c55e" if day_avg >= 0 else "#ef4444"
                day_sign = "+" if day_avg >= 0 else ""
                sum_items.append(f'<span style="font-size:0.75rem;color:#8891a0">Day <span style="font-weight:600;color:{day_color}">{day_sign}{day_avg:.1f}%</span></span>')

            summary_html = ""
            if sum_items:
                summary_html = (
                    f'<div style="display:flex;gap:1rem;padding:0.5rem 0 0.15rem;'
                    f'border-top:1px solid #2a2e3a;margin-top:0.3rem;flex-wrap:wrap">'
                    f'{"".join(sum_items)}</div>'
                )

            rows_html = "".join(row_parts)
            card_html = (
                f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
                f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
                f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_FOLDER} Portfolio</div>'
                f'{rows_html}{summary_html}</div>'
            )
        else:
            card_html = (
                f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
                f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
                f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_FOLDER} Portfolio</div>'
                f'<div style="color:#6b7280;font-size:0.8rem;padding:0.5rem 0">No holdings yet. Add a ticker above.</div>'
                f'</div>'
            )
        st.markdown(card_html, unsafe_allow_html=True)
        if portfolio:
            if st.button("Clear all holdings", key="clear_portfolio_main",
                          type="secondary", use_container_width=True):
                save_portfolio([])
                ENTRY_PRICES_FILE.write_text("{}", encoding="utf-8")
                st.session_state._skip_reanalysis = True
                st.rerun()

    with bc2:
        recs = load_track_record()
        voted = [r for r in recs if r.get("vote") is not None]
        acc = sum(1 for r in voted if r["vote"] is True) if voted else 0
        acc_pct = acc / len(voted) * 100 if voted else 0

        if voted:
            acc_color = "#22c55e" if acc_pct >= 60 else "#f59e0b" if acc_pct >= 40 else "#ef4444"
            acc_html = (
                f'<div style="text-align:center;margin:0.5rem 0">'
                f'<div style="font-size:2rem;font-weight:800;color:{acc_color};line-height:1">{acc_pct:.0f}%</div>'
                f'<div style="font-size:0.75rem;color:#8891a0;margin-top:0.15rem">{acc}/{len(voted)} correct</div></div>'
                f'<div style="height:6px;background:#1a1a2e;border-radius:3px;overflow:hidden;margin:0.4rem 0">'
                f'<div style="height:100%;width:{acc_pct:.0f}%;background:{acc_color};border-radius:3px;transition:width 0.4s"></div></div>'
            )
        else:
            acc_html = (
                '<div style="text-align:center;padding:0.5rem 0;color:#6b7280;font-size:0.85rem">'
                'No votes yet. Search a ticker and vote on the signal.</div>'
            )

        stats_html = (
            f'<div style="display:flex;justify-content:space-around;padding:0.3rem 0">'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#f0f2f5">{len(recs)}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Scans</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#22c55e">{acc}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Right</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:#ef4444">{len(voted) - acc}</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Wrong</div></div>'
            f'</div>'
        )

        st.markdown(
            f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
            f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
            f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.2);transition:border-color 0.2s ease,box-shadow 0.2s ease">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
            f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_BAR} Track Record</div>'
            f'{acc_html}{stats_html}</div>',
            unsafe_allow_html=True,
        )

    # ─── Institutional Flow Card ───
    fiidii_hist = load_fiidii_history()
    if not fiidii_hist:
        # No saved history yet — try fetching current data to create first snapshot
        fii_data = get_fii_dii_flow()
        if fii_data:
            save_fiidii_snapshot(fii_data)
            fiidii_hist = load_fiidii_history()

    if fiidii_hist:
        _INST = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>'
        latest = fiidii_hist[-1]
        fii_val = latest.get("fii_net", 0)
        dii_val = latest.get("dii_net", 0)
        net_val = fii_val + dii_val

        fii_color = "#22c55e" if fii_val >= 0 else "#ef4444"
        dii_color = "#22c55e" if dii_val >= 0 else "#ef4444"
        net_color = "#22c55e" if net_val >= 0 else "#ef4444"

        st.markdown(
            f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
            f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
            f'border-radius:12px;padding:1.25rem;margin-bottom:1rem;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.2)">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;'
            f'font-weight:600;color:#f0f2f5;margin-bottom:0.75rem">{_INST} Institutional Flow</div>'
            f'<div style="display:flex;gap:1.5rem;justify-content:space-around">'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:{fii_color}">'
            f'\u20b9{fii_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">FII/FPI</div></div>'
            f'<div style="text-align:center"><div style="font-size:1.1rem;font-weight:700;color:{dii_color}">'
            f'\u20b9{dii_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">DII</div></div>'
            f'<div style="text-align:center;padding:0 0.5rem;border-left:1px solid #2a2e3a"><div style="font-size:1.1rem;font-weight:700;color:{net_color}">'
            f'\u20b9{net_val:+,.0f} Cr</div>'
            f'<div style="font-size:0.7rem;color:#8891a0">Net</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Recent history compact table
        if len(fiidii_hist) >= 2:
            recent = fiidii_hist[-7:]  # last 7 entries
            rows = ""
            for entry in reversed(recent):
                date = entry.get("date", "")
                f = entry.get("fii_net", 0)
                d = entry.get("dii_net", 0)
                n = f + d
                fc = "#22c55e" if f >= 0 else "#ef4444"
                dc = "#22c55e" if d >= 0 else "#ef4444"
                nc = "#22c55e" if n >= 0 else "#ef4444"
                rows += (
                    f'<div style="display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;'
                    f'gap:0.5rem;padding:0.3rem 0;font-size:0.75rem;'
                    f'border-bottom:1px solid rgba(42,46,58,0.3)">'
                    f'<span style="color:#8891a0">{date}</span>'
                    f'<span style="color:{fc};text-align:right">\u20b9{f:+,.0f}</span>'
                    f'<span style="color:{dc};text-align:right">\u20b9{d:+,.0f}</span>'
                    f'<span style="color:{nc};text-align:right;font-weight:600">\u20b9{n:+,.0f}</span>'
                    f'</div>'
                )
            if rows:
                st.markdown(
                    f'<div style="background:rgba(19,21,26,0.85);backdrop-filter:blur(20px);'
                    f'-webkit-backdrop-filter:blur(20px);border:1px solid rgba(30,32,40,0.8);'
                    f'border-radius:12px;padding:0.75rem 1rem;margin:-0.5rem 0 1rem">'
                    f'<div style="display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;'
                    f'gap:0.5rem;padding:0.3rem 0;font-size:0.7rem;color:#6b7280;'
                    f'border-bottom:1px solid rgba(42,46,58,0.3)">'
                    f'<span>Date</span><span style="text-align:right">FII/FPI</span>'
                    f'<span style="text-align:right">DII</span>'
                    f'<span style="text-align:right;font-weight:600">Net</span></div>'
                    f'{rows}</div>',
                    unsafe_allow_html=True,
                )

    # ─── Sentiment History (collapsed by default) ───
    history = load_sentiment_history(final_ticker)
    if history:
        with st.expander("Sentiment History", expanded=False):
            df = pd.DataFrame(history)
            if "smartscore" in df.columns:
                df["smartscore"] = pd.to_numeric(df["smartscore"], errors="coerce")
                df = df.dropna(subset=["smartscore"])
                if not df.empty:
                    df = df.copy()
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.dropna(subset=["date"])
                    if not df.empty:
                        chart_df = df.set_index("date")[["smartscore"]]
                        st.line_chart(chart_df, y="smartscore", use_container_width=True)
            csv_data = history_to_csv(final_ticker, history)
            st.download_button(
                label="Export CSV",
                data=csv_data,
                file_name=f"{final_ticker}_sentiment_history.csv",
                mime="text/csv",
                use_container_width=True,
            )

