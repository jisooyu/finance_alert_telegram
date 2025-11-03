from dash import Dash, html

app = Dash(__name__)
server = app.server  # ✅ required for Render/Wsgi hosting

app.layout = html.Div([
    html.H1("My Dash App on Render"),
    html.P("Deployed from Raspberry Pi 🚀")
])

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8080, debug=False)
