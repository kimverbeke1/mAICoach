"""Berekening van de dip-tabel, los van Streamlit.
Gebruikt door de app (crypto_ui.py) én door de nachtelijke update (crypto_refresh.py), zodat beide exact
dezelfde tabel maken en hetzelfde opslag-sleutelwoord (cfg_key) gebruiken."""
from __future__ import annotations

import hashlib
import io
import json
from typing import Callable

import numpy as np
import pandas as pd

from crypto_dip import dip_stats, ladder_backtest

# Standaardinstellingen = de standaardwaarden van de app. De nachtelijke update rekent hiermee voor ALLE
# munten (top 150), zodat de app bij het openen meteen een kant-en-klare tabel vindt. ÉÉN plek: de app leest
# zijn standaardwaarden ook hier, zodat de opslag-sleutel altijd overeenkomt.
DEFAULT_CFG = dict(days=5 * 365 + 5, lookback=365, amount=5000.0, optimal=True, dip=0.50, target=0.30,
                   maxwait=365, min_trades=3, fee=(0.25 + 0.0) / 100, top_n=150, test_frac=0.30, only_cb=True)
# Koersdata die de nachtelijke update ververst (= ook de munten van de standaardtabel).
REFRESH_TOP_N = 150
# Wijzig je in de app een instelling, dan rekent de app opnieuw voor zoveel munten (instelbaar in de app).
LIVE_TOP_N = 75
# Instellingen die bepalen of de app de nachtelijke tabel kan gebruiken (top_n hoort er niet bij).
DEFAULT_KEYS = ("days", "lookback", "amount", "optimal", "dip", "target", "maxwait", "min_trades", "fee",
                "test_frac", "only_cb")

TEST_COLS = ["wf_params", "train_period", "train_annual_txt", "test_period", "test_status", "test_trades",
             "test_pct", "test_annual_txt", "test_eur", "test_bh_pct"]
EXTRA_TEST_COLS = ["test_buys", "test_open_days", "test_open_pct", "train_buys",
                   "train_annual_pct", "test_annual_pct", "train_short", "test_short"]
# Kolommen die er altijd moeten zijn, ook als (bijna) alle munten te weinig data hebben.
BASE_COLS = ["source", "dip_pct", "target_pct", "current_dd_pct", "to_zone_pct", "history_days", "episodes",
             "ep_text", "episode_hit_pct", "hit_rate_pct", "median_days", "median_further_pct",
             "worst_further_pct", "still_open", "bt_start", "bt_years", "dip_round_trips", "avg_hold_days",
             "capital", "final_eur", "profit_eur", "dip_annual_pct", "buy_hold_eur", "invested_pct",
             "lowest_eur", "open_cost_eur", "open_value_eur", "open_result_eur", "open_result_pct",
             "too_short", "need_days"]

OptimizeFn = Callable[[str], dict]                                  # sym -> optimize_dip-resultaat
WalkFn = Callable[[str, "tuple | None", "float | None"], dict]      # sym, fixed_tranches, fixed_target -> wf


def is_default(cfg: dict) -> bool:
    """True als alle instellingen (behalve het aantal munten) gelijk zijn aan de standaard."""
    def same(a, b):
        if isinstance(a, float) or isinstance(b, float):
            return round(float(a), 6) == round(float(b), 6)
        return a == b
    return all(same(cfg.get(k), DEFAULT_CFG[k]) for k in DEFAULT_KEYS)


def cfg_key(cfg: dict, settings: dict) -> str:
    """Sleutel voor opgeslagen resultaten: verandert zodra een instelling of een opgeslagen munt verandert."""
    norm = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in sorted(cfg.items())}
    raw = json.dumps({"cfg": norm, "settings": settings}, sort_keys=True, default=str)
    return "dip_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _flag(v) -> bool:
    """Robuust ja/nee voor kolommen met True/NaN (ook na JSON)."""
    try:
        return v is not None and not pd.isna(v) and bool(v)
    except (TypeError, ValueError):
        return False


def fmt_annual(v, short: bool = False) -> str:
    """%/jaar als tekst. Bij een periode < 0,5 jaar met waarschuwing (omrekenen naar een jaar is dan onbetrouwbaar)."""
    if v is None or pd.isna(v):
        return "–"
    s = ">999%" if v > 999 else (f"{v:.0f}%" if short else f"{v:.1f}%")
    return s + (" ⚠️ korte periode" if short else "")


def setup_text(tranches, target: float) -> str:
    """Instelling in woorden, bv. '1 schijf: koop bij −30%, doel +75%'."""
    ds = sorted(d for d, _ in tranches)
    if len(ds) == 1:
        return f"1 schijf: koop bij −{ds[0] * 100:.0f}%, doel +{target * 100:.0f}%"
    return f"{len(ds)} schijven: " + " / ".join(f"−{d * 100:.0f}%" for d in ds) + f", doel +{target * 100:.0f}%"


def coin_params(sym: str, cfg: dict, settings: dict, optimize_fn: OptimizeFn) -> dict:
    """Welke instelling geldt voor deze munt: opgeslagen > optimaal > vast. Standaard 1 schijf met het hele bedrag."""
    saved = settings.get(sym)
    if saved and saved.get("lookback") == cfg["lookback"]:
        tr = [(float(d), float(a)) for d, a in saved["tranches"]]
        return {"source": "Opgeslagen", "tranches": tr, "target": float(saved["target"]), "opt": None}
    if cfg["optimal"]:
        opt = optimize_fn(sym)
        if opt["found"]:
            return {"source": "Optimaal", "tranches": [(opt["dip"], cfg["amount"])],
                    "target": opt["target"], "opt": opt}
        return {"source": "Vast*", "tranches": [(cfg["dip"], cfg["amount"])], "target": cfg["target"], "opt": opt}
    return {"source": "Vast", "tranches": [(cfg["dip"], cfg["amount"])], "target": cfg["target"], "opt": None}


def wf_for(sym: str, p: dict, wf_fn: WalkFn) -> dict:
    """Betrouwbaarheidstest voor precies de instelling van de tabelrij (zelfde functie in tabel en detail)."""
    if p["source"] == "Optimaal":
        return wf_fn(sym, None, None)
    return wf_fn(sym, tuple((float(d), float(a)) for d, a in p["tranches"]), float(p["target"]))


def test_fields(sym: str, cfg: dict, p: dict, wf_fn: WalkFn) -> dict:
    wf = wf_for(sym, p, wf_fn)
    if not wf["wf_ok"]:
        return {"test_status": "Niet getest: " + wf["wf_reason"]}
    capital = wf["wf_capital"] if wf["wf_fixed"] else cfg["amount"]
    return {
        "wf_params": f"−{wf['wf_dip']*100:.0f}% / +{wf['wf_target']*100:.0f}%"
                     + (" (jouw instelling)" if wf["wf_fixed"] else ""),
        "train_period": f"{wf['train_start']:%m/%Y} · {wf['train_years']:.1f} j",
        "train_annual_pct": wf["train_annual_pct"], "train_short": wf["train_short"],
        "train_annual_txt": fmt_annual(wf["train_annual_pct"], wf["train_short"] and wf["train_buys"] > 0),
        "test_period": f"{wf['test_start']:%m/%Y} · {wf['test_years']:.1f} j",
        "test_status": wf["test_status"], "test_trades": wf["test_trades"],
        "test_pct": wf["test_pct"],
        "test_annual_pct": wf["test_annual_pct"], "test_short": wf["test_short"],
        "test_annual_txt": fmt_annual(wf["test_annual_pct"], wf["test_short"] and wf["test_buys"] > 0),
        "test_eur": capital * (1 + wf["test_pct"] / 100),
        "test_bh_pct": wf["test_bh_pct"], "test_buys": wf["test_buys"],
        "test_open_days": wf["test_open_days"], "test_open_pct": wf["test_open_pct"],
        "train_buys": wf["train_buys"],
    }


def verdict(r: pd.Series) -> tuple[str, str, int]:
    """(label, reden, sorteer-rang). Beoordeelt enkel op de TEST (data die de instelling niet zag)."""
    if _flag(r.get("too_short")):
        n, need = r.get("history_days"), r.get("need_days")
        n_txt = "?" if pd.isna(n) else f"{n:.0f}"
        need_txt = "?" if pd.isna(need) else f"{need:.0f}"
        return ("⚪ Te weinig data",
                f"Maar {n_txt} dagen koersdata; met deze referentieperiode zijn er minstens {need_txt} nodig. "
                "Kies bij ⚙️ Instellingen een kortere referentie (bv. 90 of 180 dagen) om deze munt mee te nemen.", 5)

    status, tp, bh = r.get("test_status"), r.get("test_pct"), r.get("test_bh_pct")
    train, trades, eps = r.get("train_annual_pct"), r.get("test_trades"), r.get("episodes")
    open_days, med, tr_buys = r.get("test_open_days"), r.get("median_days"), r.get("train_buys")
    cap, final, ann = r.get("capital"), r.get("final_eur"), r.get("dip_annual_pct")

    hist = ""
    if pd.notna(cap) and pd.notna(final) and cap > 0:
        why_not = (", maar bij 'Optimaal' is de instelling mee op de test-data afgesteld"
                   if r.get("source") == "Optimaal" else ", inclusief de testperiode")
        hist = (f" Ter vergelijking: hele historiek € {cap:,.0f} → € {final:,.0f}"
                + ("" if pd.isna(ann) else f" ({ann:.0f}%/jaar)") + why_not + ".")

    if not isinstance(status, str) or status.startswith("Niet getest") or pd.isna(tp):
        reason = status[len("Niet getest: "):] if isinstance(status, str) and status.startswith("Niet getest") \
            else "test uit"
        return "⚪ Niet getest", f"Geen training/test mogelijk ({reason}): enkel hele-historiek-cijfers." + hist, 2
    if pd.notna(train) and train <= 0:
        if pd.notna(tr_buys) and tr_buys == 0:
            return ("⚪ Niets bewezen",
                    "Ook in de trainingsperiode zakte de munt nooit tot de koopdrempel: er werd nooit gekocht." + hist, 2)
        return "🔴 Niet interessant", f"Zelfs in de training geen winst ({train:+.0f}%/jaar)." + hist, 4
    if status == "Geen koopkans":
        return ("⚪ Niets bewezen",
                "In de testperiode zakte de munt nooit tot de koopdrempel: de instelling is niet getoetst." + hist, 2)
    if tp <= 0:
        if status == "Positie open":
            dagen = "" if pd.isna(open_days) else f" (open sinds {open_days:.0f} dagen"
            if dagen and pd.notna(med):
                dagen += f"; typische wachttijd tot herstel {med:.0f} dagen"
            dagen += ")" if dagen else ""
            return ("🟠 Onder water",
                    f"Test {tp:+.0f}%: in de test gekocht tijdens de val, nog niet hersteld{dagen}. "
                    "Papieren verlies, geen bewijs dat het faalt, maar ook geen bevestiging." + hist, 3)
        return "🔴 Niet interessant", f"Test negatief ({tp:+.0f}%) zonder open positie." + hist, 4
    n = 0 if pd.isna(trades) else int(trades)
    e = 0 if pd.isna(eps) else int(eps)
    issues = []
    if status == "Positie open":
        issues.append("winst nog op papier (positie open)")
    if pd.notna(bh) and tp < bh:
        issues.append(f"kopen&houden deed beter ({bh:+.0f}% vs {tp:+.0f}%)")
    if e < 3:
        issues.append(f"weinig bewijs ({e}× in zone)")
    if issues:
        return "🟡 Twijfel", f"Test {tp:+.0f}%, maar: " + "; ".join(issues) + ".", 1
    bh_txt = "" if pd.isna(bh) else f" (kopen&houden {bh:+.0f}%)"
    return "🟢 Interessant", f"Test {tp:+.0f}%{bh_txt}, {n} afgeronde trade(s), {e}× in zone.", 0


def now_label(z) -> str:
    """Koopzone nu? Puur mechanisch, los van het oordeel."""
    if pd.isna(z):
        return "–"
    return "🛒 In koopzone" if z <= 0 else f"👀 Nog {z:.0f}% zakken"


def sort_table(t: pd.DataFrame) -> pd.DataFrame:
    """Op oordeel; binnen een oordeel op Test %/jaar, maar bij een korte test (< 0,5 jaar) op Test totaal %."""
    ann = pd.to_numeric(t["test_annual_pct"], errors="coerce")
    tot = pd.to_numeric(t["test_pct"], errors="coerce")
    short = t["test_short"].map(_flag)
    t = t.copy()
    t["_k1"] = ann.where(~short, tot).fillna(-1e9)
    t["_k2"] = pd.to_numeric(t["dip_annual_pct"], errors="coerce").fillna(-1e9)
    return t.sort_values(["_rank", "_k1", "_k2"], ascending=[True, False, False]).reset_index(drop=True)


def scan_coin(sym: str, cbt: str, cfg: dict, settings: dict, df: pd.DataFrame,
              optimize_fn: OptimizeFn, wf_fn: WalkFn) -> dict | None:
    """Eén tabelrij. Munten met te weinig data krijgen een rij '⚪ Te weinig data' (zodat ze zichtbaar blijven
    en meetellen zodra je een kortere referentie kiest). None enkel als er helemaal geen data is."""
    if df is None or len(df) == 0:
        return None
    need = cfg["lookback"] + 60
    if len(df) < need:
        return {"symbol": sym, "coinbase": cbt, "history_days": len(df), "need_days": need, "too_short": True,
                "capital": cfg["amount"], "source": "–"}
    p = coin_params(sym, cfg, settings, optimize_fn)
    first_dip = min(d for d, _ in p["tranches"])
    s = dip_stats(df, cfg["lookback"], first_dip, p["target"], cfg["maxwait"])
    bt = ladder_backtest(df, cfg["lookback"], p["tranches"], p["target"], cfg["fee"])
    if not bt.get("valid"):
        return {"symbol": sym, "coinbase": cbt, "history_days": len(df), "need_days": need, "too_short": True,
                "capital": cfg["amount"], "source": "–"}
    s.update({k: v for k, v in bt.items() if k not in ("trades", "equity", "valid")})
    s.update({
        "symbol": sym, "coinbase": cbt, "source": p["source"], "dip_pct": first_dip * 100,
        "target_pct": p["target"] * 100, "n_tranches": len(p["tranches"]), "too_short": False,
        "need_days": need,
        "to_zone_pct": max(0.0, (1 - (1 - first_dip) / (1 + s["current_dd_pct"] / 100)) * 100)
        if not np.isnan(s["current_dd_pct"]) else np.nan,
        "ep_text": f"{s['episodes_hit']} van {s['episodes_eval']}" if s["episodes_eval"] else "–",
    })
    if cfg["test_frac"] > 0:
        s.update(test_fields(sym, cfg, p, wf_fn))
    return s


def finalize(rows: list[dict]) -> pd.DataFrame:
    t = pd.DataFrame(rows)
    for c in BASE_COLS + TEST_COLS + EXTRA_TEST_COLS:
        if c not in t:
            t[c] = np.nan
    v = t.apply(verdict, axis=1, result_type="expand")
    t["verdict"], t["why"], t["_rank"] = v[0], v[1], v[2]
    t["now"] = t["to_zone_pct"].apply(now_label)
    return sort_table(t)


def table_to_json(t: pd.DataFrame) -> str:
    return t.to_json(orient="split", date_format="iso", default_handler=str)


def table_from_json(s: str) -> pd.DataFrame:
    t = pd.read_json(io.StringIO(s), orient="split", convert_dates=False)
    if "bt_start" in t:
        t["bt_start"] = pd.to_datetime(t["bt_start"], utc=True, errors="coerce")
    return t
