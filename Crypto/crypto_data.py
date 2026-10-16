"""Crypto marktdata van Coinbase (publieke Exchange-API, geen key nodig).

- Productlijst: welke munten op Coinbase verhandelbaar zijn, en in welke markten (EUR/USD/USDC/USDT).
- Top-munten op 24u-volume.
- Candles (koersbalkjes). Dagcandles worden bewaard in Firestore (via crypto_store) of lokaal (CSV) en
  INCREMENTEEL bijgewerkt: bij een refresh worden enkel de ontbrekende recente dagen opgehaald.

Symbolen zijn Coinbase product-id's, bv. 'BTC-USD'. Voor de koershistoriek wordt de USD-markt gebruikt
(langste historiek); bestaat die niet, dan USDC, dan EUR.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

import crypto_store as store

CB_URL = "https://api.exchange.coinbase.com"
HEADERS = {"User-Agent": "mAICoach-crypto/1.0", "Accept": "application/json"}
CACHE_DIR = Path(os.environ.get("CRYPTO_CACHE_DIR", Path(__file__).parent / "data_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

GRANULARITY = {"15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}   # seconden (Coinbase-waarden)
MAX_CANDLES = 299            # Coinbase geeft max. 300 candles per verzoek
REQUEST_PAUSE = 0.12         # publieke limiet ±10 verzoeken/seconde
QUOTE_PREF = ("USD", "USDC", "EUR")
CB_QUOTES = ("EUR", "USD", "USDC", "USDT")
STABLECOINS = {"USDC", "USDT", "DAI", "PYUSD", "EURC", "GUSD", "PAX", "USDP", "USDS", "TUSD", "BUSD",
               "FDUSD", "RLUSD", "USD1", "GYEN", "LUSD", "FRAX", "EUROC", "USDE", "USDG"}
CB_CACHE = CACHE_DIR / "coinbase_products_v2.json"
CANDLE_COLS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume"]


def _get(path: str, params: dict | None = None, retries: int = 4):
    for attempt in range(retries):
        try:
            r = requests.get(CB_URL + path, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 429:                       # te snel: even wachten
                time.sleep(1.0 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Coinbase: te veel verzoeken ({path})")


# --------------------------------------------------------------------------- productlijst
def _parse_products(data) -> dict[str, dict]:
    """-> {'WLD': {'quotes': ['EUR','USD'], 'ids': {'EUR': 'WLD-EUR', 'USD': 'WLD-USD'}}, ...}
    Enkel markten waar je NU effectief kan handelen (online, niet uitgeschakeld)."""
    out: dict[str, dict] = {}
    for p in data if isinstance(data, list) else []:
        base, quote, pid = p.get("base_currency"), p.get("quote_currency"), p.get("id")
        if not base or not quote or not pid:
            continue
        ok = (p.get("status", "online") == "online" and not p.get("trading_disabled")
              and not p.get("cancel_only"))
        e = out.setdefault(base, {"quotes": [], "ids": {}})
        if ok and quote in CB_QUOTES and quote not in e["quotes"]:
            e["quotes"].append(quote)
            e["ids"][quote] = pid
    for e in out.values():
        e["quotes"].sort(key=CB_QUOTES.index)
    return out


def get_coinbase_products(max_age_h: float = 24.0) -> dict:
    """{'products': {base: {...}}, 'fetched': tekst, 'stale': bool}. 24u lokaal gecached.
    Mislukt het ophalen maar bestaat er een oudere cache, dan wordt die gebruikt (stale=True)."""
    cached = None
    if CB_CACHE.exists():
        try:
            cached = json.loads(CB_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = None
    if cached and time.time() - cached.get("ts", 0) < max_age_h * 3600:
        return {**cached, "stale": False}
    try:
        products = _parse_products(_get("/products"))
        if len(products) < 20:   # onrealistisch klein => antwoord niet vertrouwen
            raise ValueError(f"slechts {len(products)} munten in antwoord")
        res = {"products": products, "ts": time.time(),
               "fetched": pd.Timestamp.now(tz="Europe/Brussels").strftime("%d/%m/%Y %H:%M")}
        CB_CACHE.write_text(json.dumps(res), encoding="utf-8")
        return {**res, "stale": False}
    except Exception as e:  # noqa: BLE001
        if cached:
            return {**cached, "stale": True}
        raise RuntimeError(f"Coinbase-productlijst niet beschikbaar: {e}") from e


def coinbase_label(products: dict | None, base: str) -> str:
    """Korte tekst voor in de tabel: in welke markten kan je deze munt op Coinbase kopen?"""
    if products is None:
        return "? (check mislukt)"
    p = products.get(base)
    if p is None:
        return "❌ niet op Coinbase"
    if not p["quotes"]:
        return "⏸️ niet verhandelbaar"
    return "✅ " + "/".join(p["quotes"])


def base_of(symbol: str) -> str:
    return symbol.split("-")[0]


def quote_of(symbol: str) -> str:
    return symbol.split("-")[1] if "-" in symbol else "USD"


def history_product(products: dict, base: str) -> str | None:
    """Product-id waarop de koershistoriek gebaseerd wordt (USD > USDC > EUR)."""
    ids = (products.get(base) or {}).get("ids", {})
    for q in QUOTE_PREF:
        if q in ids:
            return ids[q]
    return None


# --------------------------------------------------------------------------- top op volume
def _stats_all() -> dict[str, tuple[float, float]]:
    """product-id -> (24u-volume in munten, laatste koers). Eén verzoek voor alle producten."""
    data = _get("/products/stats")
    out: dict[str, tuple[float, float]] = {}
    if isinstance(data, dict):
        for pid, v in data.items():
            s = v.get("stats_24hour", v) if isinstance(v, dict) else {}
            try:
                out[pid] = (float(s.get("volume") or 0), float(s.get("last") or 0))
            except (TypeError, ValueError):
                pass
    return out


def get_top_symbols(n: int = 30) -> pd.DataFrame:
    """Top-n munten op Coinbase op 24u-handelsvolume (in USD/EUR), zonder stablecoins.
    Kolommen: symbol (product-id), base, lastPrice, quoteVolume, coinbase (markten)."""
    products = get_coinbase_products()["products"]
    cand = {}
    for base in products:
        if base in STABLECOINS:
            continue
        pid = history_product(products, base)
        if pid:
            cand[pid] = base
    try:
        stats = _stats_all()
    except Exception:  # noqa: BLE001
        stats = {}
    if not stats:     # reserve: per product opvragen (trager)
        for pid in cand:
            try:
                s = _get(f"/products/{pid}/stats")
                stats[pid] = (float(s.get("volume") or 0), float(s.get("last") or 0))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(REQUEST_PAUSE)
    rows = []
    for pid, base in cand.items():
        vol, last = stats.get(pid, (0.0, 0.0))
        rows.append({"symbol": pid, "base": base, "lastPrice": last, "quoteVolume": vol * last,
                     "coinbase": coinbase_label(products, base)})
    df = pd.DataFrame(rows, columns=["symbol", "base", "lastPrice", "quoteVolume", "coinbase"])
    df = df[df["quoteVolume"] > 0].sort_values("quoteVolume", ascending=False).head(n)
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- candles
def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_candles(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    gran = GRANULARITY[interval]
    step_ms = gran * 1000
    rows, cur = [], start_ms
    while cur < end_ms:
        nxt = min(end_ms, cur + step_ms * MAX_CANDLES)
        batch = _get(f"/products/{symbol}/candles",
                     {"granularity": gran, "start": _iso(cur), "end": _iso(nxt)})
        if isinstance(batch, list):
            rows.extend(batch)
        cur = nxt
        time.sleep(REQUEST_PAUSE)
    if not rows:
        return pd.DataFrame(columns=CANDLE_COLS)
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    for c in ("low", "high", "open", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    df["open_time"] = pd.to_numeric(df["t"]).astype("int64") * 1000
    df["quote_volume"] = df["volume"] * df["close"]
    return df[CANDLE_COLS].drop_duplicates("open_time")


def _local_path(symbol: str, interval: str) -> Path:
    return CACHE_DIR / f"{symbol}_{interval}.csv"


def _load_cache(symbol: str, interval: str) -> tuple[pd.DataFrame, dict]:
    df, meta = store.load_candles(symbol, interval)
    if df is not None:
        return df, meta
    path = _local_path(symbol, interval)
    meta_path = path.with_suffix(".json")
    df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=CANDLE_COLS)
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return df, meta


def _save_cache(symbol: str, interval: str, df: pd.DataFrame, meta: dict) -> None:
    if store.save_candles(symbol, interval, df, meta):
        return
    path = _local_path(symbol, interval)
    df.to_csv(path, index=False)
    path.with_suffix(".json").write_text(json.dumps(meta))


def get_klines(symbol: str, interval: str = "1d", days: int = 90) -> pd.DataFrame:
    """OHLCV voor de laatste `days` dagen. Incrementeel: enkel ontbrekende candles worden bij Coinbase
    opgehaald; wat al bewaard is (Firestore of lokaal) wordt hergebruikt. 'checked_from' onthoudt tot hoe
    ver terug al gezocht is, zodat jonge munten niet telkens opnieuw opgevraagd worden."""
    step = GRANULARITY[interval] * 1000
    now_ms = int(time.time() * 1000)
    want_start = now_ms - days * 86_400_000

    cached, meta = _load_cache(symbol, interval)
    meta = dict(meta or {})
    checked_from = meta.get("checked_from")
    parts = [cached] if not cached.empty else []
    changed = False

    need_older = cached.empty or (
        int(cached["open_time"].min()) > want_start + step
        and (checked_from is None or want_start < checked_from)
    )
    if need_older:
        end = int(cached["open_time"].min()) if not cached.empty else now_ms
        parts.append(_fetch_candles(symbol, interval, want_start, end))
        meta["checked_from"] = min(want_start, checked_from) if checked_from else want_start
        changed = True
    if not cached.empty:
        last = int(cached["open_time"].max())
        if last + 2 * step <= now_ms:                     # er is minstens één nieuwe, afgesloten candle
            new = _fetch_candles(symbol, interval, last + step, now_ms)
            if not new.empty:
                parts.append(new)
                changed = True

    df = pd.concat([p for p in parts if not p.empty], ignore_index=True) if parts else pd.DataFrame()
    if df.empty:
        if changed:
            _save_cache(symbol, interval, pd.DataFrame(columns=CANDLE_COLS), meta)
        return pd.DataFrame(columns=CANDLE_COLS + ["time"])
    df = df.drop_duplicates("open_time", keep="last").sort_values("open_time")
    df = df[df["open_time"] + step <= now_ms]            # lopende candle niet bewaren
    if changed:
        _save_cache(symbol, interval, df[CANDLE_COLS], meta)

    df = df[df["open_time"] >= want_start].reset_index(drop=True)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df
