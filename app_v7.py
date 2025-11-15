"""
app.py — U.S. Credit Market Dashboard (Final)
---------------------------------------------
Features:
- Fetches TOTALSLAR, BAMLH0A0HYM2, NFCI, UMCSENT, and VIXCLS from FRED
- Normalizes to z-scores for visual comparability
- Displays chart, threshold summary, and latest readings
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
    fetch_nfci, fetch_sentiment, fetch_vix
)

# ============================================================
# 1️⃣ Setup
# ============================================================
cfg = Config()
notifier = TelegramNotifier(cfg.TELEGRAM_TOKEN, cfg.CHAT_ID)
app = Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "U.S. Credit Market Dashboard"

# ============================================================
# 2️⃣ Data Loader
# ============================================================
def load_data():
    cc = fetch_consumer_credit(cfg.START_DATE)
    hy = fetch_hy_spread(cfg.START_DATE)
    nf = fetch_nfci(cfg.START_DATE)
    sent = fetch_sentiment(cfg.START_DATE)
    vix = fetch_vix(cfg.START_DATE)

    cc = cc.rename(columns={"pct_change_consumer_credit": "Consumer Credit Growth (%)"})
    hy = hy.rename(columns={"hy_oas_bps": "HY Spread (bps)"})
    nf = nf.rename(columns={"nfci": "NFCI Index"})
    sent = sent.rename(columns={"consumer_sentiment": "Consumer Sentiment Index"})
    vix = vix.rename(columns={"vix": "VIX Index"})

    df = cc[["Consumer Credit Growth (%)"]].join(
        hy[["HY Spread (bps)"]], how="outer"
    ).join(nf[["NFCI Index"]], how="outer").join(
        sent[["Consumer Sentiment Index"]], how="outer"
    ).join(vix[["VIX Index"]], how="outer")

    df = df.sort_index().ffill()
    df = df[df.index >= (df.index.max() - pd.DateOffset(years=2))]
    return df


# ============================================================
# 3️⃣ Chart Builder (raw data)
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

    fig = go.Figure()

    # --- Add traces for all 5 indicators ---
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Consumer Credit Growth (%)"],
        name="Consumer Credit Growth (%)",
        line=dict(color="blue", width=2), yaxis="y"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["HY Spread (bps)"],
        name="HY Spread (bps)",
        line=dict(color="red", width=2), yaxis="y2"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["NFCI Index"],
        name="NFCI Index",
        line=dict(color="green", width=2, dash="dash"), yaxis="y3"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Consumer Sentiment Index"],
        name="Consumer Sentiment Index",
        line=dict(color="purple", width=2, dash="dot"), yaxis="y4"
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["VIX Index"],
        name="VIX Index",
        line=dict(color="orange", width=2, dash="dot"), yaxis="y5"
    ))

    # --- Layout with all positions ≤ 1.0 ---
    fig.update_layout(
        title="U.S. Credit Market Indicators (Raw Values)",
        xaxis=dict(title="Date"),

        # Left axis
        yaxis=dict(
            title=dict(text="Consumer Credit Growth (%)", font=dict(color="blue")),
            tickfont=dict(color="blue")
        ),

        # Right-side stacked axes (0.90 to 0.995)
        yaxis2=dict(
            title=dict(text="HY Spread (bps)", font=dict(color="red")),
            tickfont=dict(color="red"),
            overlaying="y", side="right", position=0.90
        ),
        yaxis3=dict(
            title=dict(text="NFCI Index", font=dict(color="green")),
            tickfont=dict(color="green"),
            overlaying="y", side="right", position=0.94
        ),
        yaxis4=dict(
            title=dict(text="Consumer Sentiment", font=dict(color="purple")),
            tickfont=dict(color="purple"),
            overlaying="y", side="right", position=0.97
        ),
        yaxis5=dict(
            title=dict(text="VIX", font=dict(color="orange")),
            tickfont=dict(color="orange"),
            overlaying="y", side="right", position=0.995
        ),

        legend=dict(orientation="h", y=-0.25),
        template="plotly_white",
        height=650
    )

    # --- Add threshold lines (within valid ranges) ---
    try:
        fig.add_hline(y=cfg.CREDIT_THRESHOLD, line_dash="dot", line_color="blue",
                      annotation_text="Credit Thresh")
        fig.add_hline(y=cfg.HY_SPREAD_THRESHOLD, line_dash="dot", line_color="red",
                      annotation_text="HY Thresh")
        fig.add_hline(y=cfg.NFCI_THRESHOLD, line_dash="dot", line_color="green",
                      annotation_text="NFCI Thresh")
        fig.add_hline(y=cfg.SENTIMENT_THRESHOLD, line_dash="dot", line_color="purple",
                      annotation_text="Sentiment Thresh")
        fig.add_hline(y=cfg.VIX_THRESHOLD, line_dash="dot", line_color="orange",
                      annotation_text="VIX Thresh")
    except Exception as e:
        print(f"[Warning] Could not draw threshold lines: {e}")

    return fig

# ============================================================
# 4️⃣ Threshold Display
# ============================================================
def make_threshold_cards(cfg: Config):
    thresholds = {
        "Consumer Credit Growth (%)": f"< {cfg.CREDIT_THRESHOLD:.2f}%",
        "HY Spread (bps)": f"> {cfg.HY_SPREAD_THRESHOLD:.0f} bps",
        "NFCI Index": f"> {cfg.NFCI_THRESHOLD:.2f}",
        "Consumer Sentiment Index": f"< {cfg.SENTIMENT_THRESHOLD:.0f}",
        "VIX Index": f"> {cfg.VIX_THRESHOLD:.0f}"
    }

    cards = []
    for k, v in thresholds.items():
        cards.append(
            dbc.Card(
                dbc.CardBody([
                    html.H6(k, className="card-title"),
                    html.P(v, className="card-text fw-bold text-danger mb-0")
                ]),
                className="text-center shadow-sm",
                style={"width": "13rem", "margin": "6px"}
            )
        )

    return dbc.Row(
        [dbc.Col(card, width="auto") for card in cards],
        justify="center",
        className="mb-4"
    )


# ============================================================
# 5️⃣ Summary Table Builder
# ============================================================
def make_summary_table(df: pd.DataFrame):
    latest_records = []
    for col in df.columns:
        last_rows = df[[col]].dropna().tail(3)
        for idx, val in last_rows.iterrows():
            latest_records.append({
                "Indicator": col,
                "Date": idx.strftime("%Y-%m-%d"),
                "Value": round(val[col], 2)
            })
    table_df = pd.DataFrame(latest_records)

    return dash_table.DataTable(
        data=table_df.to_dict("records"),
        columns=[{"name": i, "id": i} for i in table_df.columns],
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "padding": "6px"},
        style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold"},
        page_size=15
    )


# ============================================================
# 6️⃣ Layout
# ============================================================
app.layout = dbc.Container([
    html.H2("📊 U.S. Credit Market Dashboard"),
    html.P("Tracking Consumer Credit (TOTALSLAR), HY Spread (BAMLH0A0HYM2), NFCI, "
           "Consumer Sentiment (UMCSENT), and VIX (VIXCLS)."),

    # Chart
    dcc.Graph(id="credit_chart", style={"height": "600px"}),
    html.Br(),

    # Thresholds Section
    html.H5("📉 Alert Thresholds"),
    html.Div(id="threshold_cards"),
    html.Br(),

    # Summary Table
    html.H5("Latest Readings"),
    html.Div(id="summary_table"),
    html.Br(),

    # Telegram Section
    dbc.Button("🚀 Send Telegram Summary", id="send_btn", color="success", className="me-2"),
    html.Span(id="status", className="text-info"),
    html.Br(),

    # Auto-refresh
    dcc.Interval(
        id="weekly_refresh",
        interval=7 * 24 * 3600 * 1000,
        n_intervals=0
    )
], fluid=True, className="p-4")


# ============================================================
# 7️⃣ Callbacks
# ============================================================
@app.callback(
    Output("credit_chart", "figure"),
    Output("summary_table", "children"),
    Output("threshold_cards", "children"),
    Input("weekly_refresh", "n_intervals"),
)
def update_dashboard(n_intervals):
    df = load_data()
    fig = make_chart(df)
    table = make_summary_table(df)
    cards = make_threshold_cards(cfg)
    return fig, table, cards


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
        f"• VIX: {latest['VIX Index']:.2f}"
    )
    asyncio.run(notifier.send(msg))
    return f"✅ Telegram summary sent at {datetime.now().strftime('%H:%M:%S')}"


# ============================================================
# 8️⃣ Run
# ============================================================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=True)
