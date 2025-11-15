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
# 3️⃣ Chart Builder (Z-Score Normalization)
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

    # --- Compute z-score normalization ---
    df_norm = (df - df.mean()) / df.std()

    # --- Compute threshold z-scores ---
    thresh_values = {
        "Consumer Credit Growth (%)": (cfg.CREDIT_THRESHOLD - df["Consumer Credit Growth (%)"].mean()) / df["Consumer Credit Growth (%)"].std(),
        "HY Spread (bps)": (cfg.HY_SPREAD_THRESHOLD - df["HY Spread (bps)"].mean()) / df["HY Spread (bps)"].std(),
        "NFCI Index": (cfg.NFCI_THRESHOLD - df["NFCI Index"].mean()) / df["NFCI Index"].std(),
        "Consumer Sentiment Index": (cfg.SENTIMENT_THRESHOLD - df["Consumer Sentiment Index"].mean()) / df["Consumer Sentiment Index"].std(),
        "VIX Index": (cfg.VIX_THRESHOLD - df["VIX Index"].mean()) / df["VIX Index"].std()
    }

    colors = {
        "Consumer Credit Growth (%)": "blue",
        "HY Spread (bps)": "red",
        "NFCI Index": "green",
        "Consumer Sentiment Index": "purple",
        "VIX Index": "orange"
    }

    fig = go.Figure()

    # --- Plot normalized data (solid lines) ---
    for col, color in colors.items():
        fig.add_trace(go.Scatter(
            x=df_norm.index, y=df_norm[col],
            mode="lines", name=col,
            line=dict(color=color, width=2)
        ))

    # --- Plot dashed threshold lines (same color) ---
    for col, color in colors.items():
        z_thresh = thresh_values[col]
        fig.add_hline(
            y=z_thresh,
            line_dash="dot",
            line_color=color,
            annotation_text=f"{col} thresh (z={z_thresh:.2f})",
            annotation_position="top right",  # 🟢 move labels to right edge
            annotation_font=dict(size=10, color=color)
        )

    # --- Expand vertical range for readability ---
    y_min = df_norm.min().min()
    y_max = df_norm.max().max()
    margin = (y_max - y_min) * 0.3  # add 30% margin
    fig.update_yaxes(range=[y_min - margin, y_max + margin])

    fig.update_layout(
        title="Normalized U.S. Credit Market Indicators (Z-Scores)",
        xaxis_title="Date",
        yaxis_title="Standardized Value (Z-Score)",
        template="plotly_white",
        height=650,  # slightly taller
        legend=dict(orientation="h", y=-0.25)
    )

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
