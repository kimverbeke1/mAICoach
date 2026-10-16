"""Nachtelijke update (GitHub Actions): koersdata bijwerken in Firestore en de dip-tabel met de
standaardinstellingen berekenen en bewaren, zodat de app bij het openen meteen een tabel heeft.

Lokaal testen:  python crypto_refresh.py            (vanuit de map Crypto)
Omgeving:       FIREBASE_SERVICE_ACCOUNT_JSON  (JSON-tekst van de service account)
                CRYPTO_REQUIRE_CLOUD=1         -> stop met fout als Firestore niet bereikbaar is
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
from crypto_scan import DEFAULT_CFG, cfg_key, finalize, scan_coin, table_to_json  # noqa: E402


def main() -> int:
    t0 = time.time()
    print(f"Opslag: {store.status()}")
    if os.environ.get("CRYPTO_REQUIRE_CLOUD") == "1" and not store.is_cloud():
        print("FOUT: Firestore niet bereikbaar (controleer de secret FIREBASE_SERVICE_ACCOUNT_JSON).")
        return 1
    cfg = dict(DEFAULT_CFG)
    settings = cs.load_all()
    tops = get_top_symbols(cfg["top_n"])
    print(f"{len(tops)} munten: {', '.join(tops['symbol'])}")

    @lru_cache(maxsize=None)
    def klines(sym: str):
        return get_klines(sym, "1d", cfg["days"])

    def opt_fn(sym):
        return optimize_dip(klines(sym), cfg["lookback"], cfg["fee"], cfg["min_trades"])

    def wf_fn(sym, tr, tg):
        fixed = None if tr is None else {"tranches": list(tr), "target": tg}
        return walk_forward(klines(sym), cfg["lookback"], cfg["fee"], cfg["min_trades"], cfg["test_frac"], fixed)

    rows, errors = [], 0
    for sym, cbt in zip(tops["symbol"], tops["coinbase"]):
        try:
            r = scan_coin(sym, cbt, cfg, settings, klines(sym), opt_fn, wf_fn)
            print(f"  {sym:12s} {len(klines(sym)):5d} dagen  {'ok' if r else 'te weinig data'}")
            if r:
                rows.append(r)
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  {sym:12s} FOUT: {e}")
    if not rows:
        print("Geen enkele munt berekend.")
        return 1
    t = finalize(rows)
    key = cfg_key(cfg, settings)
    store.save_result(key, table_to_json(t), source="github")
    print(f"Tabel bewaard onder {key}: {len(t)} munten, {errors} fouten, {time.time() - t0:.0f} s.")
    print(t[["symbol", "verdict", "now"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
