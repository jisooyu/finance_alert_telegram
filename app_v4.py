"""
app.py — U.S. Credit Market Dashboard (Final)
---------------------------------------------
Features:
- Fetches TOTALSLAR, BAMLH0A0HYM2, and NFCI from FRED
- Normalizes to z-scores for clear comparison
- Displays 3-axis chart + summary table of latest readings
- Auto-refreshes weekly
- Telegram summary alert button
"""

import asyncio
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, dash_table, Output, Input
import dash_bootstrap_components as dbc

from credit_monitor_extended import (
    Config, TelegramNotifier,
    fetch_consumer_credit, fetch_hy_spread,
    fetch_nfci, fetch_sentiment, fetch_vix  # 🟠 added
)

# ============================================================
# 1️⃣ Setup
# ============================================================
cfg = Config()
notifier = TelegramNotifier(cfg.TELEGRAM_TOKEN, cfg.CHAT_ID)
app = Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "Credit Market Dashboard"

# ============================================================
# 2️⃣ Data loader
# ============================================================
def load_data():
    cc = fetch_consumer_credit(cfg.START_DATE)
    hy = fetch_hy_spread(cfg.START_DATE)
    nf = fetch_nfci(cfg.START_DATE)
    sent = fetch_sentiment(cfg.START_DATE)
    vix = fetch_vix(cfg.START_DATE)  # 🟠 new

    cc = cc.rename(columns={"pct_change_consumer_credit": "Consumer Credit Growth (%)"})
    hy = hy.rename(columns={"hy_oas_bps": "HY Spread (bps)"})
    nf = nf.rename(columns={"nfci": "NFCI Index"})
    sent = sent.rename(columns={"consumer_sentiment": "Consumer Sentiment Index"})
    vix = vix.rename(columns={"vix": "VIX Index"})  # 🟠 new

    df = (
        cc[["Consumer Credit Growth (%)"]]
        .join(hy[["HY Spread (bps)"]], how="outer")
        .join(nf[["NFCI Index"]], how="outer")
        .join(sent[["Consumer Sentiment Index"]], how="outer")
        .join(vix[["VIX Index"]], how="outer")  # 🟠 join VIX
    )

    df = df.sort_index().ffill()
    df = df[df.index >= (df.index.max() - pd.DateOffset(years=2))]
    return df


# ============================================================
# 3️⃣ Chart builder
# ============================================================
def make_chart(df):
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="⚠️ No data available from FRED.",
            xref="paper", yref="paper", showarrow=False,
            font=dict(size=16, color="red"), x=0.5, y=0.5
        )
        return fig

    # Normalize each series to Z-scores for visibility
    df_norm = (df - df.mean()) / df.std()

    fig = go.Figure()
    colors = {
        "Consumer Credit Growth (%)": "blue",
        "HY Spread (bps)": "red",
        "NFCI Index": "green",
        "Consumer Sentiment Index": "purple",
        "VIX Index": "orange",  # 🟠 new color
    }

    for col, color in colors.items():
        fig.add_trace(go.Scatter(
            x=df_norm.index, y=df_norm[col],
            mode="lines", name=col,
            line=dict(
                color=color, width=2,
                dash="dash" if col in ["NFCI Index", "Consumer Sentiment Index", "VIX Index"] else "solid"
            )
        ))

    fig.update_layout(
        title="Normalized U.S. Credit Market Indicators + VIX (Z-Scores)",
        xaxis_title="Date",
        yaxis_title="Standardized Value (Z-Score)",
        template="plotly_white", height=600,
        legend=dict(orientation="h", y=-0.25)
    )
    return fig

# ============================================================
# 6️⃣ Telegram Summary
# ============================================================
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
        f"• NFCI: {latest['NFCI Index']:.2f}\n"
        f"• Sentiment: {latest['Consumer Sentiment Index']:.2f}\n"
        f"• VIX: {latest['VIX Index']:.2f}"  # 🟠 new line
    )
    asyncio.run(notifier.send(msg))
    return f"✅ Telegram summary sent at {datetime.now().strftime('%H:%M:%S')}"

# ============================================================
# 5️⃣ Layout
# ============================================================
app.layout = dbc.Container([
    html.H2("📊 U.S. Credit Market Dashboard"),
    html.P("Tracking Consumer Credit (TOTALSLAR), HY Spread (BAMLH0A0HYM2), "
           "Financial Conditions (NFCI), University of Michigan Sentiment (UMCSENT), "
           "and VIX Volatility Index (VIXCLS)."),

    dcc.Graph(id="credit_chart", style={"height": "600px"}),
    html.Br(),

    html.H5("Latest Readings"),
    html.Div(id="summary_table"),
    html.Br(),

    dbc.Button("🚀 Send Telegram Summary", id="send_btn", color="success", className="me-2"),
    html.Span(id="status", className="text-info"),
    html.Br(),

    dcc.Interval(
        id="weekly_refresh",
        interval=7 * 24 * 3600 * 1000,  # auto-refresh weekly
        n_intervals=0
    )
], fluid=True, className="p-4")


# ============================================================
# 6️⃣ Callbacks
# ============================================================
@app.callback(
    Output("credit_chart", "figure"),
    Output("summary_table", "children"),
    Input("weekly_refresh", "n_intervals"),
)
def update_dashboard(n_intervals):
    df = load_data()
    fig = make_chart(df)

    if df.empty:
        return fig, html.P("⚠️ No data available", className="text-danger")

    # Build latest-values summary table — include ALL columns (including VIX)
    latest_dates = []
    for col in df.columns:
        last_rows = df[[col]].dropna().tail(3)
        for idx, val in last_rows.iterrows():
            latest_dates.append({
                "Indicator": col,
                "Date": idx.strftime("%Y-%m-%d"),
                "Value": round(val[col], 2)
            })

    table_df = pd.DataFrame(latest_dates)

    table = dash_table.DataTable(
        data=table_df.to_dict("records"),
        columns=[{"name": i, "id": i} for i in table_df.columns],
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "padding": "6px"},
        style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold"},
        page_size=15,  # ⬆️ slightly higher to fit all 5 indicators × 3 rows
    )

    return fig, table
# ============================================================
# 7️⃣ Run
# ============================================================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=True)
