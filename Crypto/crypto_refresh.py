"""Nachtelijke update (GitHub Actions):
  1. koersdata bijwerken in Firestore voor de Coinbase-top REFRESH_TOP_N (standaard 150) munten,
     zodat de data ook klaarstaat als je overdag meer munten kiest dan de standaard;
  2. de dip-tabel met de standaardinstellingen (DEFAULT_CFG, standaard top 75) berekenen en bewaren,
     zodat de app bij het openen meteen een tabel heeft.

Lokaal testen:  python crypto_refresh.py            (vanuit de map Crypto)
Omgeving:       FIREBASE_SERVICE_ACCOUNT_JSON  (JSON-tekst van de service account)
                CRYPTO_REQUIRE_CLOUD=1         -> stop met fout als Firestore niet bereikbaar is
                CRYPTO_REFRESH_TOP_N=200       -> optioneel ander aantal munten voor de koersdata
"""
from __future__ import annotations

import os
import sys
import time
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import crypto_settings as cs  # noqa: E402
import crypto_store as store  # noqa: E402
from crypto_data import get_klines, get_top_symbols  # noqa: E402
from crypto_dip import optimize_dip, walk_forward  # noqa: E402
from crypto_scan import DEFAULT_CFG, REFRESH_TOP_N, cfg_key, finalize, scan_coin, table_to_json  # noqa: E402


def _refresh_n(table_n: int) -> int:
    raw = (os.environ.get("CRYPTO_REFRESH_TOP_N") or "").strip()
    try:
        n = int(raw) if raw else REFRESH_TOP_N
    except ValueError:
        n = REFRESH_TOP_N
    return max(n, table_n)          # nooit minder data dan de tabel nodig heeft


def main() -> int:
    t0 = time.time()
    print(f"Opslag: {store.status()}")
    if os.environ.get("CRYPTO_REQUIRE_CLOUD") == "1" and not store.is_cloud():
        print("FOUT: Firestore niet bereikbaar (controleer de secret FIREBASE_SERVICE_ACCOUNT_JSON).")
        return 1
    cfg = dict(DEFAULT_CFG)
    settings = cs.load_all()
    n_data = _refresh_n(cfg["top_n"])
    tops = get_top_symbols(n_data)                    # gesorteerd op 24u-volume
    table_syms = set(tops["symbol"].head(cfg["top_n"]))
    print(f"Koersdata voor {len(tops)} munten, tabel voor de top {len(table_syms)}.")

    @lru_cache(maxsize=None)
    def klines(sym: str):
        return get_klines(sym, "1d", cfg["days"])

    def opt_fn(sym):
        return optimize_dip(klines(sym), cfg["lookback"], cfg["fee"], cfg["min_trades"])

    def wf_fn(sym, tr, tg):
        fixed = None if tr is None else {"tranches": list(tr), "target": tg}
        return walk_forward(klines(sym), cfg["lookback"], cfg["fee"], cfg["min_trades"], cfg["test_frac"], fixed)

    rows, errors = [], 0
    t_data = t_calc = 0.0
    for i, (sym, cbt) in enumerate(zip(tops["symbol"], tops["coinbase"]), 1):
        try:
            s0 = time.time()
            n_days = len(klines(sym))
            d_data = time.time() - s0
            t_data += d_data
            msg = f"data {d_data:5.1f}s"
            if sym in table_syms:
                s1 = time.time()
                r = scan_coin(sym, cbt, cfg, settings, klines(sym), opt_fn, wf_fn)
                d_calc = time.time() - s1
                t_calc += d_calc
                msg += f"  berekening {d_calc:5.1f}s  {'ok' if r else 'te weinig data'}"
                if r:
                    rows.append(r)
            else:
                msg += "  (enkel data)"
            print(f"  {i:3d}. {sym:14s} {n_days:5d} dagen  {msg}", flush=True)
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  {i:3d}. {sym:14s} FOUT: {e}", flush=True)
    if not rows:
        print("Geen enkele munt berekend.")
        return 1
    t = finalize(rows)
    key = cfg_key(cfg, settings)
    store.save_result(key, table_to_json(t), source="github")
    print(f"Tabel bewaard onder {key}: {len(t)} munten, {errors} fouten. "
          f"Tijd: data {t_data:.0f}s, berekening {t_calc:.0f}s, totaal {time.time() - t0:.0f}s.")
    print(t[["symbol", "verdict", "now"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
