"""Berekening van de dip-tabel, los van Streamlit.
Gebruikt door de app (crypto_ui.py) én door de nachtelijke update (crypto_refresh.py), zodat beide exact
dezelfde tabel maken en hetzelfde opslag-sleutelwoord (cfg_key) gebruiken.

Twee soorten instellingen:
  - REKEN-instellingen (historiek, referentie, bedrag, modus, kosten, aantal testvensters, ...): bepalen de
    berekening en dus de opslag-sleutel. Wijzigen = opnieuw rekenen.
  - OORDEEL-drempels (min. rendement per jaar, min. gerealiseerde trades, max. diepte open positie): bepalen enkel
    het oordeel. Wijzigen = meteen nieuw oordeel, zonder opnieuw te rekenen."""
from __future__ import annotations

import hashlib
import io
import json
import math
from typing import Callable

import numpy as np
import pandas as pd

from crypto_dip import dip_stats, is_stable, ladder_backtest, top_info

# Ingebouwde standaard. Wat je met '💾 Bewaar als standaard' opslaat (crypto_store.load_app_defaults) gaat voor.
BASE_DEFAULTS = dict(days=8 * 365 + 5, lookback=365, amount=5000.0, optimal=True, dip=0.50, target=0.30,
                     maxwait=365, min_trades=3, fee=0.25 / 100, top_n=150, n_windows=3, only_cb=True)
VERDICT_DEFAULTS = dict(min_annual=15.0, min_real_trades=3, max_open_dd=20.0)
# Instellingen die je als standaard kan bewaren (kosten niet: die komen uit het kosten-blok).
SAVABLE_CALC = ("days", "lookback", "amount", "optimal", "dip", "target", "maxwait", "min_trades", "top_n",
                "n_windows")
# Instellingen die bepalen of de app de nachtelijke tabel kan gebruiken (top_n hoort er niet bij).
DEFAULT_KEYS = ("days", "lookback", "amount", "optimal", "dip", "target", "maxwait", "min_trades", "fee",
                "n_windows", "only_cb")
# De nachtelijke update ververst de koersdata voor minstens zoveel munten.
REFRESH_TOP_N = 150
# Standaard aantal munten als de app zelf herberekent (gewijzigde instellingen).
LIVE_TOP_N = 150

# Achterwaartse compatibiliteit (oudere imports)
DEFAULT_CFG = dict(BASE_DEFAULTS)

TEST_COLS = ["wf_settings", "stable_txt", "test_period", "win_text", "real_trades", "real_total_pct",
             "real_annual_pct", "open_now_pct", "total_annual_pct", "bh_annual_pct"]
EXTRA_TEST_COLS = ["test_status", "n_win", "win_pos", "win_active", "buys_test", "stable", "open_now_days",
                   "test_years", "short_test", "total_total_pct", "bh_total_pct", "windows_json"]
BASE_COLS = ["source", "dip_pct", "target_pct", "current_dd_pct", "to_zone_pct", "history_days", "episodes",
             "ep_text", "episode_hit_pct", "hit_rate_pct", "median_days", "median_further_pct",
             "worst_further_pct", "still_open", "bt_start", "bt_years", "dip_round_trips", "avg_hold_days",
             "capital", "final_eur", "profit_eur", "dip_annual_pct", "buy_hold_eur", "invested_pct",
             "lowest_eur", "open_cost_eur", "open_value_eur", "open_result_eur", "open_result_pct",
             "too_short", "need_days", "price_now", "buy_level", "sell_level", "top_price"]

OptimizeFn = Callable[[str], dict]
WalkFn = Callable[[str, "tuple | None", "float | None"], dict]     # sym, fixed_tranches, fixed_target -> wf


def effective_defaults(stored: dict | None) -> tuple[dict, dict]:
    """(reken-standaard, oordeel-standaard) = ingebouwd, overschreven door wat je bewaarde."""
    calc, verd = dict(BASE_DEFAULTS), dict(VERDICT_DEFAULTS)
    for k, v in (stored or {}).items():
        if k in SAVABLE_CALC:
            calc[k] = v
        elif k in VERDICT_DEFAULTS:
            verd[k] = v
    return calc, verd


def is_default(cfg: dict, defaults: dict) -> bool:
    """True als alle reken-instellingen (behalve het aantal munten) gelijk zijn aan de standaard."""
    def same(a, b):
        if isinstance(a, float) or isinstance(b, float):
            try:
                return round(float(a), 6) == round(float(b), 6)
            except (TypeError, ValueError):
                return False
        return a == b
    return all(same(cfg.get(k), defaults.get(k)) for k in DEFAULT_KEYS)


def cfg_key(cfg: dict, settings: dict) -> str:
    """Sleutel voor opgeslagen resultaten (enkel reken-instellingen + per munt opgeslagen instellingen)."""
    calc = {k: cfg[k] for k in list(DEFAULT_KEYS) + ["top_n"] if k in cfg}
    norm = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in sorted(calc.items())}
    raw = json.dumps({"cfg": norm, "settings": settings, "v": 2}, sort_keys=True, default=str)
    return "dip_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _flag(v) -> bool:
    try:
        return v is not None and not pd.isna(v) and bool(v)
    except (TypeError, ValueError):
        return False


def _num(v) -> float:
    try:
        f = float(v)
        return f if not math.isnan(f) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _int(v) -> int:
    f = _num(v)
    return 0 if math.isnan(f) else int(f)


def fmt_annual(v, short: bool = False) -> str:
    if v is None or pd.isna(v):
        return "–"
    s = ">999%" if v > 999 else (f"{v:.0f}%" if short else f"{v:.1f}%")
    return s + (" ⚠️ korte periode" if short else "")


def setup_text(tranches, target: float) -> str:
    ds = sorted(d for d, _ in tranches)
    if len(ds) == 1:
        return f"1 schijf: koop bij −{ds[0] * 100:.0f}%, doel +{target * 100:.0f}%"
    return f"{len(ds)} schijven: " + " / ".join(f"−{d * 100:.0f}%" for d in ds) + f", doel +{target * 100:.0f}%"


def coin_params(sym: str, cfg: dict, settings: dict, optimize_fn: OptimizeFn) -> dict:
    """Instelling voor deze munt VANDAAG: opgeslagen > optimaal (over de hele historiek) > vast."""
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
    """Testvensters voor precies de werkwijze/instelling van de tabelrij (zelfde functie in tabel en detail)."""
    if p["source"] == "Optimaal":
        return wf_fn(sym, None, None)
    return wf_fn(sym, tuple((float(d), float(a)) for d, a in p["tranches"]), float(p["target"]))


def _windows_to_json(rows: list[dict]) -> str:
    def conv(v):
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
        if isinstance(v, (np.floating, float)):
            return None if math.isnan(float(v)) else float(v)
        if isinstance(v, np.integer):
            return int(v)
        return v
    return json.dumps([{k: conv(v) for k, v in r.items()} for r in rows])


def windows_from_json(s) -> list[dict]:
    if not isinstance(s, str) or not s:
        return []
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return []


def test_fields(sym: str, cfg: dict, p: dict, wf_fn: WalkFn) -> dict:
    wf = wf_for(sym, p, wf_fn)
    if not wf["wf_ok"]:
        return {"test_status": "Niet getest: " + wf["wf_reason"],
                "windows_json": _windows_to_json(wf.get("windows", []))}
    sets = wf["settings"]
    if wf["wf_fixed"]:
        stable = None                                   # vaste instelling: stabiliteit is niet van toepassing
        stable_txt = "n.v.t. (vaste instelling)"
    else:
        today = (min(d for d, _ in p["tranches"]), p["target"]) if p["source"] == "Optimaal" else None
        stable = is_stable(sets + ([today] if today else []))
        stable_txt = "–" if stable is None else ("✅ stabiel" if stable else "⚠️ instabiel")
    return {
        "test_status": "OK",
        "wf_settings": " · ".join(f"−{d * 100:.0f}/+{t * 100:.0f}" for d, t in sets),
        "stable": stable, "stable_txt": stable_txt,
        "test_period": f"{pd.Timestamp(wf['test_start']):%m/%Y} → {pd.Timestamp(wf['test_end']):%m/%Y} · "
                       f"{wf['test_years']:.1f} j",
        "test_years": wf["test_years"], "short_test": wf["short_test"],
        "n_win": wf["n_windows"], "win_pos": wf["win_pos"], "win_active": wf["win_active"],
        "win_text": f"{wf['win_pos']} van {wf['n_windows']}",
        "real_trades": wf["real_trades"], "buys_test": wf["buys"],
        "real_total_pct": wf["real_total_pct"], "real_annual_pct": wf["real_annual_pct"],
        "total_total_pct": wf["total_total_pct"], "total_annual_pct": wf["total_annual_pct"],
        "bh_total_pct": wf["bh_total_pct"], "bh_annual_pct": wf["bh_annual_pct"],
        "open_now_pct": wf["open_now_pct"], "open_now_days": wf["open_now_days"],
        "windows_json": _windows_to_json(wf["windows"]),
    }


def verdict(r: pd.Series, v: dict) -> tuple[str, str, int]:
    """(label, reden, sorteer-rang). Beoordeelt op de TESTVENSTERS (blind getest), met de nadruk op
    GEREALISEERDE winst. v = oordeel-drempels (min_annual, min_real_trades, max_open_dd)."""
    if _flag(r.get("too_short")):
        n, need = _num(r.get("history_days")), _num(r.get("need_days"))
        return ("⚪ Te weinig data",
                f"Maar {n:.0f} dagen koersdata; met deze referentieperiode zijn er minstens {need:.0f} nodig. "
                "Kies bij ⚙️ Instellingen een kortere referentie (bv. 90 of 180 dagen) om deze munt mee te nemen.", 5)
    status = r.get("test_status")
    if not isinstance(status, str) or status != "OK":
        reason = status[len("Niet getest: "):] if isinstance(status, str) and status.startswith("Niet getest") \
            else "testvensters uit"
        return "⚪ Niet getest", f"Geen testvenster mogelijk ({reason}): enkel hele-historiek-cijfers.", 2

    R = _int(r.get("real_trades"))
    buys = _int(r.get("buys_test"))
    ra, ta = _num(r.get("real_annual_pct")), _num(r.get("total_annual_pct"))
    rt = _num(r.get("real_total_pct"))
    bh = _num(r.get("bh_annual_pct"))
    on = _num(r.get("open_now_pct"))
    od = _num(r.get("open_now_days"))
    med = _num(r.get("median_days"))
    nw, wp = _int(r.get("n_win")), _int(r.get("win_pos"))
    stable = r.get("stable")
    if not isinstance(stable, (bool, np.bool_)):
        stable = None if (stable is None or (isinstance(stable, float) and math.isnan(stable))) else bool(stable)
    short = _flag(r.get("short_test"))
    yrs = _num(r.get("test_years"))
    real_txt = (f"gerealiseerd {rt:+.0f}% over {yrs:.1f} j" if short
                else f"gerealiseerd {ra:+.0f}%/jaar over {yrs:.1f} j")
    bh_txt = "" if math.isnan(bh) else f" Kopen&houden: {bh:+.0f}%/jaar."
    open_txt = "" if math.isnan(on) else f"; laatste positie open {on:+.0f}%" + \
        ("" if math.isnan(od) else f" (sinds {od:.0f} dagen)")

    if buys == 0:
        return ("⚪ Niets bewezen",
                f"In de {nw} testvenster(s) zakte de munt nooit tot de koopdrempel: de werkwijze is niet getoetst.", 2)

    score_ra = rt if short else ra                    # bij een korte test het totaal, niet het jaarcijfer
    min_ann = float(v["min_annual"])
    good = (R >= int(v["min_real_trades"]) and not math.isnan(score_ra) and score_ra >= min_ann
            and stable is not False and (math.isnan(on) or on >= -float(v["max_open_dd"])) and 2 * wp >= nw)
    if good:
        return ("🟢 Interessant",
                f"{real_txt.capitalize()}, {R} afgeronde trade(s), positief in {wp} van {nw} vensters"
                + (", instelling stabiel" if stable else "") + open_txt + "." + bh_txt, 0)

    deep_open = not math.isnan(on) and on < -float(v["max_open_dd"])
    if deep_open and (R < int(v["min_real_trades"]) or math.isnan(score_ra) or score_ra < min_ann):
        wait = "" if math.isnan(med) else f"; typische wachttijd tot herstel {med:.0f} dagen"
        return ("🟠 Onder water",
                f"Laatste positie staat {on:+.0f}%" + ("" if math.isnan(od) else f" (open sinds {od:.0f} dagen")
                + wait + (")" if not math.isnan(od) else "") + f"; {real_txt}, {R} afgeronde trade(s). "
                "Papieren verlies: nog niet hersteld." + bh_txt, 3)

    if not math.isnan(ra) and ra < 0 and (math.isnan(ta) or ta <= 0):
        return ("🔴 Niet interessant", f"{real_txt.capitalize()} en ook inclusief open positie geen winst "
                f"({ta:+.0f}%/jaar), {R} afgeronde trade(s)." + bh_txt, 4)

    issues = []
    if R < int(v["min_real_trades"]):
        issues.append(f"te weinig afgeronde trades ({R} < {int(v['min_real_trades'])})")
    if math.isnan(score_ra) or score_ra < min_ann:
        issues.append(f"gerealiseerd rendement onder je minimum ({score_ra:+.0f}% < {min_ann:.0f}%)")
    if stable is False:
        issues.append("instelling instabiel tussen de vensters")
    if deep_open:
        issues.append(f"laatste positie {on:+.0f}% (dieper dan −{float(v['max_open_dd']):.0f}%)")
    if 2 * wp < nw:
        issues.append(f"maar {wp} van {nw} vensters positief")
    return ("🟡 Twijfel", f"{real_txt.capitalize()}, maar: " + "; ".join(issues) + "." + bh_txt, 1)


def now_label(z) -> str:
    if pd.isna(z):
        return "–"
    return "🛒 In koopzone" if z <= 0 else f"👀 Nog {z:.0f}% zakken"


def sort_table(t: pd.DataFrame) -> pd.DataFrame:
    """Op oordeel; binnen een oordeel op gerealiseerd rendement per jaar (bij korte test: gerealiseerd totaal)."""
    ra = pd.to_numeric(t["real_annual_pct"], errors="coerce")
    rt = pd.to_numeric(t["real_total_pct"], errors="coerce")
    short = t["short_test"].map(_flag)
    t = t.copy()
    t["_k1"] = ra.where(~short, rt).fillna(-1e9)
    t["_k2"] = pd.to_numeric(t["dip_annual_pct"], errors="coerce").fillna(-1e9)
    return t.sort_values(["_rank", "_k1", "_k2"], ascending=[True, False, False]).reset_index(drop=True)


def apply_verdicts(t: pd.DataFrame, v: dict) -> pd.DataFrame:
    """Oordeel opnieuw bepalen met (nieuwe) drempels, zonder te herberekenen."""
    t = t.copy()
    for c in BASE_COLS + TEST_COLS + EXTRA_TEST_COLS:
        if c not in t:
            t[c] = np.nan
    res = t.apply(lambda r: verdict(r, v), axis=1, result_type="expand")
    t["verdict"], t["why"], t["_rank"] = res[0], res[1], res[2]
    t["now"] = t["to_zone_pct"].apply(now_label)
    return sort_table(t)


def scan_coin(sym: str, cbt: str, cfg: dict, settings: dict, df: pd.DataFrame,
              optimize_fn: OptimizeFn, wf_fn: WalkFn) -> dict | None:
    """Eén tabelrij. Munten met te weinig data krijgen een rij '⚪ Te weinig data'."""
    if df is None or len(df) == 0:
        return None
    need = cfg["lookback"] + 60
    short_row = {"symbol": sym, "coinbase": cbt, "history_days": len(df), "need_days": need, "too_short": True,
                 "capital": cfg["amount"], "source": "–"}
    if len(df) < need:
        return short_row
    p = coin_params(sym, cfg, settings, optimize_fn)
    first_dip = min(d for d, _ in p["tranches"])
    s = dip_stats(df, cfg["lookback"], first_dip, p["target"], cfg["maxwait"])
    bt = ladder_backtest(df, cfg["lookback"], p["tranches"], p["target"], cfg["fee"])
    if not bt.get("valid"):
        return short_row
    ti = top_info(df, cfg["lookback"], [first_dip], p["target"])
    s.update({k: v for k, v in bt.items() if k not in ("trades", "equity", "valid")})
    s.update({
        "symbol": sym, "coinbase": cbt, "source": p["source"], "dip_pct": first_dip * 100,
        "target_pct": p["target"] * 100, "n_tranches": len(p["tranches"]), "too_short": False,
        "need_days": need, "price_now": ti["price"], "top_price": ti["top"],
        "buy_level": ti["levels"][0]["buy_level"], "sell_level": ti["levels"][0]["sell_target"],
        "to_zone_pct": max(0.0, (1 - (1 - first_dip) / (1 + s["current_dd_pct"] / 100)) * 100)
        if not np.isnan(s["current_dd_pct"]) else np.nan,
        "ep_text": f"{s['episodes_hit']} van {s['episodes_eval']}" if s["episodes_eval"] else "–",
    })
    if cfg.get("n_windows", 0) > 0:
        s.update(test_fields(sym, cfg, p, wf_fn))
    return s


def finalize(rows: list[dict], v: dict | None = None) -> pd.DataFrame:
    return apply_verdicts(pd.DataFrame(rows), v or VERDICT_DEFAULTS)


def table_to_json(t: pd.DataFrame) -> str:
    return t.to_json(orient="split", date_format="iso", default_handler=str)


def table_from_json(s: str) -> pd.DataFrame:
    t = pd.read_json(io.StringIO(s), orient="split", convert_dates=False)
    if "bt_start" in t:
        t["bt_start"] = pd.to_datetime(t["bt_start"], utc=True, errors="coerce")
    return t
