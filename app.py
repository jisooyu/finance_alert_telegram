"""
app.py — Credit Market Dashboard (Fixed)
----------------------------------------
Visualizes:
- Consumer Credit Growth (TOTALSLAR)
- HY Spread (BAMLH0A0HYM2)
- NFCI Index
Auto-refreshes weekly and supports Telegram alerts.
"""

import asyncio
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, Output, Input
import dash_bootstrap_components as dbc

from credit_monitor_extended import (
    Config, TelegramNotifier,
    fetch_consumer_credit, fetch_hy_spread, fetch_nfci
)

# ============================================================
# 1️⃣ Setup
# ============================================================
cfg = Config()
notifier = TelegramNotifier(cfg.TELEGRAM_TOKEN, cfg.CHAT_ID)
app = Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "Credit Market Dashboard"

# ============================================================
# 2️⃣ Data Loader
# ============================================================
def load_data():
    """Fetch and merge all indicators with frequency alignment."""
    try:
        cc = fetch_consumer_credit(cfg.START_DATE)
        hy = fetch_hy_spread(cfg.START_DATE)
        nf = fetch_nfci(cfg.START_DATE)

        # Rename key columns
        cc = cc.rename(columns={"pct_change_consumer_credit": "Consumer Credit Growth (%)"})
        hy = hy.rename(columns={"hy_oas_bps": "HY Spread (bps)"})
        nf = nf.rename(columns={"nfci": "NFCI Index"})

        # Merge using outer join on DATE
        df = cc[["Consumer Credit Growth (%)"]].join(
            hy[["HY Spread (bps)"]], how="outer"
        ).join(nf[["NFCI Index"]], how="outer")

        # Sort & forward-fill lower-frequency data
        df = df.sort_index().ffill()

        # Optional: limit to last 2 years for visibility
        df = df[df.index >= (df.index.max() - pd.DateOffset(years=2))]

        print(f"[DEBUG] Loaded merged data tail:\n{df.tail()}")
        return df

    except Exception as e:
        print(f"[ERROR] Data load failed: {e}")
        return pd.DataFrame()


# ============================================================
# 3️⃣ Chart builder
# ============================================================
def make_chart(df):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index, y=df["Consumer Credit Growth (%)"],
        mode="lines", name="Consumer Credit Growth (%)",
        line=dict(color="blue", width=2), yaxis="y"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["HY Spread (bps)"],
        mode="lines", name="HY Spread (bps)",
        line=dict(color="red", width=2), yaxis="y2"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["NFCI Index"],
        mode="lines", name="NFCI Index",
        line=dict(color="green", width=2, dash="dash"), yaxis="y3"
    ))

    fig.update_layout(
        title="U.S. Credit Market Indicators (Multiple Scales)",
        xaxis=dict(title="Date"),
        yaxis=dict(title=dict(text="Consumer Credit Growth (%)",
                              font=dict(color="blue")),
                   tickfont=dict(color="blue")),
        yaxis2=dict(title=dict(text="HY Spread (bps)",
                               font=dict(color="red")),
                    tickfont=dict(color="red"),
                    overlaying="y", side="right", position=0.9),
        yaxis3=dict(title=dict(text="NFCI Index",
                               font=dict(color="green")),
                    tickfont=dict(color="green"),
                    overlaying="y", side="right", position=1.0),
        legend=dict(orientation="h", y=-0.25),
        template="plotly_white", height=600
    )
    return fig


# ============================================================
# 4️⃣ Layout
# ============================================================
app.layout = dbc.Container([
    html.H2("📊 U.S. Credit Market Dashboard"),
    html.P("Tracking Consumer Credit (TOTALSLAR), HY Spread (BAMLH0A0HYM2), and Financial Conditions (NFCI)."),

    dcc.Graph(id="credit_chart", style={"height": "600px"}),
    html.Br(),

    dbc.Button("🚀 Send Telegram Summary", id="send_btn", color="success", className="me-2"),
    html.Span(id="status", className="text-info"),
    html.Br(),

    dcc.Interval(
        id="weekly_refresh",
        interval=7 * 24 * 3600 * 1000,   # every 7 days
        n_intervals=0
    )
], fluid=True, className="p-4")

# ============================================================
# 5️⃣ Callbacks
# ============================================================
@app.callback(
    Output("credit_chart", "figure"),
    Input("weekly_refresh", "n_intervals"),
)
def update_chart(n_intervals):
    df = load_data()
    return make_chart(df)


@app.callback(
    Output("status", "children"),
    Input("send_btn", "n_clicks"),
    prevent_initial_call=True
)
def send_summary(n_clicks):
    df = load_data()
    if df.empty:
        return "⚠️ Data unavailable — cannot send summary."
    latest = df.iloc[-1]
    msg = (
        f"📊 <b>Credit Dashboard Update ({datetime.now():%Y-%m-%d %H:%M})</b>\n"
        f"• Consumer Credit: {latest['Consumer Credit Growth (%)']:.2f}%\n"
        f"• HY Spread: {latest['HY Spread (bps)']:.0f} bps\n"
        f"• NFCI: {latest['NFCI Index']:.2f}"
    )
    asyncio.run(notifier.send(msg))
    return f"✅ Telegram summary sent at {datetime.now().strftime('%H:%M:%S')}"

# ============================================================
# 6️⃣ Run
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)
