import asyncio
import threading
from datetime import datetime

import pandas as pd
from dash import Dash, html, dcc, Output, Input, dash_table
import dash_bootstrap_components as dbc

from credit_monitor_extended import Config, TelegramNotifier, fetch_consumer_credit, fetch_hy_spread, fetch_nfci

# ============================================================
# 1️⃣ Setup
# ============================================================
cfg = Config()
notifier = TelegramNotifier(cfg.TELEGRAM_TOKEN, cfg.CHAT_ID)
app = Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "Credit Market Monitor"

# ============================================================
# 2️⃣ Data loading helper
# ============================================================
def load_data():
    cc = fetch_consumer_credit(cfg.START_DATE)
    hy = fetch_hy_spread(cfg.START_DATE)
    nf = fetch_nfci(cfg.START_DATE)

    latest = pd.DataFrame({
        "Indicator": ["Consumer Credit Growth (%)", "HY Spread (bps)", "NFCI Index"],
        "Latest Value": [
            round(cc.iloc[-1]["pct_change_consumer_credit"], 2),
            round(hy.iloc[-1]["hy_oas_bps"], 0),
            round(nf.iloc[-1]["nfci"], 2)
        ],
        "Last Updated": [
            cc.index.max().strftime("%Y-%m-%d"),
            hy.index.max().strftime("%Y-%m-%d"),
            nf.index.max().strftime("%Y-%m-%d")
        ]
    })
    return latest

# ============================================================
# 3️⃣ Layout
# ============================================================
app.layout = dbc.Container([
    html.H2("📊 US Credit Market Dashboard"),
    html.P("Monitors Consumer Credit(TOTALSLAR), HY Spread(BAMLH0A0HYM2), and Financial Conditions (NFCI)."),

    html.Div(id="data_table"),
    html.Br(),

    dbc.Button("🔄 Refresh Data", id="refresh_btn", color="primary", className="me-2"),
    dbc.Button("🚀 Send Telegram Summary", id="send_btn", color="success"),
    html.Div(id="status", className="mt-3 text-info"),

    dcc.Interval(id="auto_refresh", interval=3600 * 1000, n_intervals=0)  # hourly refresh
], fluid=True, className="p-4")

# ============================================================
# 4️⃣ Callbacks
# ============================================================

@app.callback(
    Output("data_table", "children"),
    Input("refresh_btn", "n_clicks"),
    Input("auto_refresh", "n_intervals"),
)
def update_table(n_clicks, n_intervals):
    df = load_data()
    table = dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": i, "id": i} for i in df.columns],
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "padding": "6px"},
        style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold"},
    )
    return table


@app.callback(
    Output("status", "children"),
    Input("send_btn", "n_clicks"),
    prevent_initial_call=True
)
def send_summary(n_clicks):
    df = load_data()
    msg = (
        f"📊 *Credit Dashboard Update ({datetime.now():%Y-%m-%d %H:%M})*\n"
        f"• Consumer Credit: {df.iloc[0]['Latest Value']}%\n"
        f"• HY Spread: {df.iloc[1]['Latest Value']} bps\n"
        f"• NFCI: {df.iloc[2]['Latest Value']}"
    )
    asyncio.run(notifier.send(msg))
    return f"✅ Telegram alert sent at {datetime.now().strftime('%H:%M:%S')}"

# ============================================================
# 5️⃣ Run server
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)

