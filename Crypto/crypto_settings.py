"""Per munt opgeslagen dip-instellingen (koopdrempel, winstdoel, schijven).
In de cloud in Firestore (crypto_settings/coins), anders lokaal in coin_settings.json."""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import crypto_store as store

SETTINGS_FILE = Path(os.environ.get("CRYPTO_SETTINGS_FILE", Path(__file__).parent / "coin_settings.json"))
_cache: dict = {"data": None, "ts": 0.0}
_TTL = 60  # seconden: tijdens één analyse niet tientallen keren Firestore lezen


def _read() -> dict:
    data = store.load_settings()
    if data is not None:
        return data
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _write(data: dict) -> None:
    if not store.save_settings(data):
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _cache.update(data=data, ts=time.time())


def load_all() -> dict:
    if _cache["data"] is None or time.time() - _cache["ts"] > _TTL:
        _cache.update(data=_read(), ts=time.time())
    return dict(_cache["data"])


def get(symbol: str) -> dict | None:
    return load_all().get(symbol)


def save(symbol: str, target: float, tranches: list[tuple[float, float]], lookback: int) -> None:
    data = _read()
    data[symbol] = {"target": float(target), "lookback": int(lookback),
                    "tranches": [[float(d), float(a)] for d, a in tranches],
                    "updated": date.today().isoformat()}
    _write(data)


def delete(symbol: str) -> None:
    data = _read()
    if data.pop(symbol, None) is not None:
        _write(data)
