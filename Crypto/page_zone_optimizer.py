"""
page_zone_optimizer.py - Streamlit-pagina: beste koop/verkoop-drempels.
  Tab 1: overzicht - per munt de beste betrouwbare combinatie
  Tab 2: detail    - heatmap en trades voor één munt
Lokaal:  streamlit run page_zone_optimizer.py   (vanuit de map Crypto)
Later :  from page_zone_optimizer import render_zone_optimizer
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_fetcher import fetch_candles
from zone_optimizer import (buy_and_hold_pct, optimize, period_info, robust_best,
                            simulate, summarize_symbol)

FEE_PRESETS = {
    "Coinbase Advanced - limiet, < $1K/30d (0,60%)": 0.60,
    "Coinbase Advanced - markt, < $1K/30d (1,20%)": 1.20,
    "Coinbase Advanced - limiet, $1K-$10K/30d (0,40%)": 0.40,
    "Coinbase Advanced - limiet, $10K-$50K/30d (0,25%)": 0.25,
    "Zelf invullen": None,
}
COINS = ["WLDUSDT", "FETUSDT", "FILUSDT", "NEARUSDT", "TAOUSDT", "SUIUSDT", "ADAUSDT",
         "DOGEUSDT", "XRPUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "ETHUSDT", "BTCUSDT"]

LABELS = {
    "koop_bij_daling_pct": "Koop bij daling (%)",
    "verkoop_bij_stijging_pct": "Verkoop bij stijging (%)",
    "afgeronde_trades": "Trades (volledig)",
    "eindwaarde": "Eindwaarde (€)",
    "rendement_pct": "Rendement volledige periode (%)",
    "rendement_per_jaar_pct": "Rendement per jaar (%)",
    "rendement_training_pct": "Rendement training (%)",
    "trades_training": "Trades training",
    "rendement_test_pct": "Rendement test (%)",
    "trades_test": "Trades test",
    "max_drawdown_pct": "Max drawdown (%)",
    "tijd_in_munt_pct": "Tijd in munt (%)",
    "open_positie_einde": "Open positie op einde",
    "open_positie_resultaat_pct": "Open positie op papier (%)",
}
OVERVIEW_LABELS = {
    "munt": "Munt", "periode": "Periode", "dagen": "Dagen",
    "beste_koop_daling_pct": "Koop bij daling (%)",
    "beste_verkoop_stijging_pct": "Verkoop bij stijging (%)",
    "trades": "Trades", "eindwaarde": "€1000 werd (€)",
    "rendement_pct": "Rendement (%)", "rendement_per_jaar_pct": "Per jaar (%)",
    "kopen_laten_staan_pct": "Kopen & laten staan (%)",
    "beter_dan_laten_staan": "Beter dan laten staan?",
    "rendement_test_pct": "Test (%)", "trades_test": "Trades test",
    "max_drawdown_pct": "Max drawdown (%)", "tijd_in_munt_pct": "Tijd in munt (%)",
    "oordeel": "Oordeel",
}


def _settings(key: str, with_symbol: bool):
    cols = st.columns(4 if with_symbol else 3)
    i = 0
    symbol = None
    if with_symbol:
        symbol = cols[0].selectbox("Munt", COINS, key=f"{key}_sym")
        i = 1
    days = cols[i].selectbox("Periode (dagen terug)", [90, 180, 365, 730], index=2, key=f"{key}_days")
    interval = cols[i + 1].selectbox("Candle-interval", ["1h", "4h", "1d"], index=1, key=f"{key}_int",
                                     help="1 candle = 1 koersblokje. Kleiner = nauwkeuriger, trager.")
    preset = cols[i + 2].selectbox("Kosten", list(FEE_PRESETS), key=f"{key}_fee")
    fee = FEE_PRESETS[preset]
    if fee is None:
        fee = cols[i + 2].number_input("Kost per order (%)", 0.0, 3.0, 0.60, 0.05, key=f"{key}_feeval")
    return symbol, days, interval, fee


def _period_text(df):
    p = period_info(df)
    return (f"**Periode:** {p['start']:%d/%m/%Y} → {p['einde']:%d/%m/%Y} ({p['dagen']} dagen). "
            f"**Training:** {p['start']:%d/%m/%Y} → {p['training_tot']:%d/%m/%Y} ({p['dagen_training']} d). "
            f"**Test:** {p['test_vanaf']:%d/%m/%Y} → {p['einde']:%d/%m/%Y} ({p['dagen_test']} d).")


def _heatmap(res: pd.DataFrame):
    piv = res.pivot(index="koop_bij_daling_pct", columns="verkoop_bij_stijging_pct",
                    values="rendement_pct").sort_index()
    trades = res.pivot(index="koop_bij_daling_pct", columns="verkoop_bij_stijging_pct",
                       values="afgeronde_trades").sort_index()
    text = [[f"{v:+.0f}%<br>{int(t)}x" for v, t in zip(rv, rt)]
            for rv, rt in zip(piv.values, trades.values)]
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=[f"+{c}%" for c in piv.columns], y=[f"-{i}%" for i in piv.index],
        text=text, texttemplate="%{text}", colorscale="RdYlGn", zmid=0,
        colorbar=dict(title="Rendement")))
    fig.update_layout(xaxis_title="Verkopen bij stijging t.o.v. aankoop",
                      yaxis_title="Kopen bij daling t.o.v. top", height=560)
    return fig


def _trade_chart(df, trades, open_entry):
    fig = go.Figure(go.Scatter(x=df["time"], y=df["close"], name="Koers", line=dict(width=1)))
    fig.add_scatter(x=[df["time"].iloc[b] for b, *_ in trades], y=[p for _, _, p, _ in trades],
                    mode="markers", marker=dict(color="green", size=10, symbol="triangle-up"),
                    name="Koop")
    fig.add_scatter(x=[df["time"].iloc[s] for _, s, _, _ in trades], y=[p for *_, p in trades],
                    mode="markers", marker=dict(color="red", size=10, symbol="triangle-down"),
                    name="Verkoop")
    if open_entry:
        fig.add_hline(y=open_entry, line_dash="dot", annotation_text="open positie (aankoopprijs)")
    test_start = df["time"].iloc[int(len(df) * 0.7)]
    fig.add_vline(x=test_start, line_dash="dash", line_color="gray")
    fig.add_annotation(x=test_start, y=1, yref="paper", text="start testperiode", showarrow=False)
    fig.update_layout(height=420)
    return fig


def _render_overview(start_cash):
    st.caption("Per munt de beste combinatie die óók in de testperiode effectief handelde en winst gaf.")
    _, days, interval, fee = _settings("ov", with_symbol=False)
    coins = st.multiselect("Munten", COINS, default=COINS)
    if not st.button("Bereken overzicht", type="primary"):
        return
    rows, bar = [], st.progress(0.0)
    for n, sym in enumerate(coins, 1):
        try:
            rows.append(summarize_symbol(sym, fetch_candles(sym, interval, days), fee, start_cash))
        except Exception as e:  # munt niet beschikbaar e.d.
            rows.append({"munt": sym, "oordeel": f"fout: {e}"})
        bar.progress(n / len(coins))
    df = pd.DataFrame(rows).sort_values("rendement_per_jaar_pct", ascending=False, na_position="last")
    df = df[[c for c in OVERVIEW_LABELS if c in df.columns]].rename(columns=OVERVIEW_LABELS)
    st.dataframe(df.round(1), use_container_width=True, hide_index=True)
    st.download_button("Download als CSV", df.to_csv(index=False, sep=";", decimal=","),
                       "zone_overzicht.csv", "text/csv")


def _render_detail(start_cash):
    symbol, days, interval, fee = _settings("dt", with_symbol=True)
    if not st.button("Bereken detail", type="primary"):
        return
    with st.spinner("Koersen ophalen en combinaties doorrekenen..."):
        df = fetch_candles(symbol, interval, days)
        res = optimize(df, fee, start_cash=start_cash)
    st.markdown(_period_text(df))
    bh = buy_and_hold_pct(df, fee)
    best, robust = res.iloc[0], robust_best(res)

    m1, m2, m3 = st.columns(3)
    m1.metric("Hoogste rendement (volledige periode)",
              f"-{best.koop_bij_daling_pct:g}% / +{best.verkoop_bij_stijging_pct:g}%",
              f"{best.rendement_pct:+.1f}% ({int(best.afgeronde_trades)} trades)")
    m2.metric("Kopen en laten staan", f"{bh:+.1f}%")
    if robust is not None:
        m3.metric("Beste betrouwbare combinatie",
                  f"-{robust.koop_bij_daling_pct:g}% / +{robust.verkoop_bij_stijging_pct:g}%",
                  f"test {robust.rendement_test_pct:+.1f}% ({int(robust.trades_test)} trades)")
    else:
        m3.metric("Beste betrouwbare combinatie", "geen")

    st.markdown("**Heatmap** - per vakje: rendement over de volledige periode en aantal afgeronde trades.")
    st.plotly_chart(_heatmap(res), use_container_width=True)

    choice = robust if robust is not None else best
    sim = simulate(df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(),
                   choice.koop_bij_daling_pct, choice.verkoop_bij_stijging_pct, fee,
                   start_cash, return_trades=True)
    st.markdown(f"**Trades voor -{choice.koop_bij_daling_pct:g}% / +{choice.verkoop_bij_stijging_pct:g}%**")
    if sim["open_positie_einde"]:
        st.warning(f"Op het einde zit de simulatie nog in de munt (open positie): "
                   f"{sim['open_positie_resultaat_pct']:+.1f}% op papier.")
    st.plotly_chart(_trade_chart(df, sim["trades"], sim["open_aankoopprijs"]), use_container_width=True)

    with st.expander("Alle combinaties (tabel)"):
        cols = [c for c in LABELS if c in res.columns]
        st.dataframe(res[cols].rename(columns=LABELS).round(1), use_container_width=True, hide_index=True)
    with st.expander("Hoe lees ik dit?"):
        st.markdown("""
Er lopen **drie aparte simulaties**, elk opnieuw met het startbedrag:
- **Volledige periode** - de hele periode in één keer.
- **Training** - enkel de eerste 70%.
- **Test** - enkel de laatste 30%, alsof je pas dan begint.

De drie getallen tel je dus **niet** op. Test = 0% met 0 trades betekent: in die laatste periode
zakte de koers nooit genoeg om te kopen, je geld bleef cash.
**Rendement per jaar** maakt periodes van verschillende lengte vergelijkbaar.
""")


def render_zone_optimizer():
    st.header("🎯 Beste koop/verkoop-drempels (historisch)")
    start_cash = st.number_input("Startbedrag (€)", 100.0, 100000.0, 1000.0, 100.0)
    t1, t2 = st.tabs(["Overzicht per munt", "Detail één munt"])
    with t1:
        _render_overview(start_cash)
    with t2:
        _render_detail(start_cash)


if __name__ == "__main__":
    st.set_page_config(page_title="Crypto - drempels", page_icon="🎯", layout="wide")
    render_zone_optimizer()
