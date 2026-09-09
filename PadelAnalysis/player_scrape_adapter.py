# -*- coding: utf-8 -*-
"""
player_scrape_adapter.py
------------------------
PadelAnalysis - Adapter die de BESTAANDE spelerscraper in jouw repo opzoekt
en aanroept, ongeacht hoe de module of functie exact heet.

Waarom dit bestand bestaat:
  De tegenstanderanalyse toonde "nog niet gescrapet" omdat er geen scraper
  gevonden werd. Deze adapter scant het hele PadelAnalysis-pakket naar een
  callable die 1 speler kan scrapen, en probeert meerdere signatures.

Publieke API:
    find_scraper()            -> (callable, "module.functie") of (None, None)
    scrape_player(name, url)  -> dict met genormaliseerde spelerdata
    normalize(raw, name)      -> dict -> standaardschema
    diagnostics()             -> dict met wat er gevonden werd (voor debug-paneel)

Standaardschema dat deze module teruggeeft:
    {
      "player_id": str,
      "name": str,
      "profile_url": str | None,
      "current_ranking": str | None,
      "best_ranking": str | None,
      "best_ranking_date": "YYYY-MM-DD" | None,
      "ranking_history": [ {"date": "YYYY-MM-DD", "ranking": "P300"} , ... ],
      "matches": [ {"date","poule","team","opponent","partner","result","won"} , ... ],
      "partners": [ {"partner","matches","wins"} , ... ],
      "last_scraped": ISO-timestamp,
      "scrape_source": "module.functie",
    }
"""

from __future__ import annotations

import datetime as _dt
import importlib
import inspect
import pkgutil
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Kandidaten: eerst expliciet, daarna automatische scan
# ---------------------------------------------------------------------------

EXPLICIT_CANDIDATES: List[Tuple[str, str]] = [
    ("PadelAnalysis.scraper.player_playwright", "scrape_player"),
    ("PadelAnalysis.scraper.poule_playwright", "scrape_player"),
    ("PadelAnalysis.scraper.scrape_player", "scrape_player"),
    ("PadelAnalysis.scraper.scraper", "scrape_player"),
    ("PadelAnalysis.opponent_scout", "scrape_player"),
    ("PadelAnalysis.opponent_scout", "scrape_opponent"),
    ("PadelAnalysis.scrape_padel", "scrape_player"),
    ("scraper.player_playwright", "scrape_player"),
    ("scraper.scrape_player", "scrape_player"),
    ("opponent_scout", "scrape_player"),
    ("opponent_scout", "scrape_opponent"),
    ("scrape_padel", "scrape_player"),
]

# Pakketten die automatisch doorzocht worden als niets hierboven werkt
SCAN_PACKAGES = ["PadelAnalysis", "PadelAnalysis.scraper", "scraper", ""]

# Functienamen die als "speler scrapen" tellen
FUNCTION_NAME_PATTERNS = [
    r"^scrape_player$", r"^scrape_speler$", r"^scrape_opponent$",
    r"^fetch_player$", r"^get_player_data$", r"^player_dossier$",
    r"^scrape_player_profile$", r"^scrape_profile$", r"^scout_player$",
]

_RANK_RE = re.compile(r"[Pp]\s*\d{2,4}|\b\d{2,4}\b")

_cached: Optional[Tuple[Optional[Callable], Optional[str]]] = None
_diag: Dict[str, Any] = {"tried": [], "found": None, "candidates_seen": []}


# ---------------------------------------------------------------------------
# Scraper opzoeken
# ---------------------------------------------------------------------------

def _try_import(mod_name: str):
    try:
        return importlib.import_module(mod_name) if mod_name else None
    except Exception as exc:
        _diag["tried"].append(f"{mod_name}: import faalde ({type(exc).__name__})")
        return None


def _scan_package(pkg_name: str) -> List[Tuple[Callable, str]]:
    """Zoek in een pakket naar functies die op een spelerscraper lijken."""
    found: List[Tuple[Callable, str]] = []
    pkg = _try_import(pkg_name) if pkg_name else None
    module_names: List[str] = []

    if pkg is not None and hasattr(pkg, "__path__"):
        for _, name, _ in pkgutil.iter_modules(pkg.__path__):
            module_names.append(f"{pkg_name}.{name}")
    elif pkg is not None:
        module_names.append(pkg_name)

    for mod_name in module_names:
        mod = _try_import(mod_name)
        if mod is None:
            continue
        for fn_name, fn in vars(mod).items():
            if not callable(fn) or inspect.isclass(fn):
                continue
            if any(re.match(p, fn_name) for p in FUNCTION_NAME_PATTERNS):
                found.append((fn, f"{mod_name}.{fn_name}"))
                _diag["candidates_seen"].append(f"{mod_name}.{fn_name}")
    return found


def find_scraper(force: bool = False) -> Tuple[Optional[Callable], Optional[str]]:
    """Geef (functie, "module.functie") van de eerste bruikbare spelerscraper."""
    global _cached
    if _cached is not None and not force:
        return _cached

    for mod_name, fn_name in EXPLICIT_CANDIDATES:
        mod = _try_import(mod_name)
        if mod is None:
            continue
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            _diag["found"] = f"{mod_name}.{fn_name}"
            _cached = (fn, f"{mod_name}.{fn_name}")
            return _cached

    for pkg in SCAN_PACKAGES:
        hits = _scan_package(pkg)
        if hits:
            fn, label = hits[0]
            _diag["found"] = label
            _cached = (fn, label)
            return _cached

    _cached = (None, None)
    return _cached


def diagnostics() -> Dict[str, Any]:
    find_scraper()
    return dict(_diag)


# ---------------------------------------------------------------------------
# Aanroepen met meerdere mogelijke signatures
# ---------------------------------------------------------------------------

def _call_scraper(fn: Callable, name: str, url: Optional[str]) -> Any:
    attempts: List[Tuple[tuple, dict]] = []
    if url:
        attempts += [((url,), {}), ((), {"url": url}), ((), {"profile_url": url}),
                     ((name, url), {}), ((), {"name": name, "url": url})]
    attempts += [((name,), {}), ((), {"name": name}), ((), {"player_name": name}),
                 ((), {"speler": name}), ((), {"query": name})]

    last_exc: Optional[Exception] = None
    for args, kwargs in attempts:
        try:
            return fn(*args, **kwargs)
        except TypeError as exc:
            last_exc = exc
            continue
    if last_exc:
        raise last_exc
    return None


# ---------------------------------------------------------------------------
# Normaliseren
# ---------------------------------------------------------------------------

def _pick(d: Dict[str, Any], keys: List[str], default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, "", [], {}):
            return d[k]
    for nested in ("profile", "data", "info", "stats"):
        sub = d.get(nested) if isinstance(d, dict) else None
        if isinstance(sub, dict):
            for k in keys:
                if sub.get(k) not in (None, "", [], {}):
                    return sub[k]
    return default


def _date_str(value: Any) -> Optional[str]:
    if value in (None, "", []):
        return None
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%Y", "%Y-%m"):
        try:
            return _dt.datetime.strptime(s[:10] if len(s) >= 10 else s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(20\d{2})[-/ ]?(\d{1,2})?", s)
    if m:
        y = int(m.group(1)); mo = int(m.group(2) or 1)
        return f"{y:04d}-{min(max(mo, 1), 12):02d}-01"
    return None


def _rank_str(value: Any) -> Optional[str]:
    if value in (None, "", []):
        return None
    m = _RANK_RE.search(str(value))
    if not m:
        return None
    token = m.group(0).replace(" ", "").upper()
    return token if token.startswith("P") else f"P{token}"


def rank_value(ranking: Any) -> Optional[int]:
    """P300 -> 300. Lager = sterker."""
    s = _rank_str(ranking)
    if not s:
        return None
    try:
        return int(s[1:])
    except ValueError:
        return None


def _normalize_history(raw: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(raw, dict):
        raw = [{"date": k, "ranking": v} for k, v in raw.items()]
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            item = {"date": item[0], "ranking": item[1]}
        if not isinstance(item, dict):
            continue
        d = _date_str(_pick(item, ["date", "datum", "period", "periode", "season", "seizoen"]))
        r = _rank_str(_pick(item, ["ranking", "klassement", "rank", "value", "waarde"]))
        if d and r:
            out.append({"date": d, "ranking": r})
    out.sort(key=lambda x: x["date"])
    # dedupe op datum, laatste wint
    dedup: Dict[str, str] = {}
    for row in out:
        dedup[row["date"]] = row["ranking"]
    return [{"date": d, "ranking": r} for d, r in sorted(dedup.items())]


def _normalize_matches(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        result = _pick(m, ["result", "resultaat", "score", "uitslag"])
        won = _pick(m, ["won", "win", "gewonnen", "is_win"])
        if won is None and isinstance(result, str):
            wl = result.strip().lower()
            if wl.startswith(("w", "g")):
                won = True
            elif wl.startswith(("l", "v")):
                won = False
        out.append({
            "date": _date_str(_pick(m, ["date", "datum", "match_date", "speeldatum"])),
            "poule": _pick(m, ["poule", "reeks", "poule_name", "reeks_naam", "series"]),
            "team": _pick(m, ["team", "ploeg", "my_team", "eigen_ploeg"]),
            "opponent": _pick(m, ["opponent", "tegenstander", "away_team", "uitploeg"]),
            "partner": _pick(m, ["partner", "teammate", "medespeler", "partner_name"]),
            "result": result,
            "won": bool(won) if won is not None else None,
        })
    return out


def _derive_partners(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    agg: Dict[str, Dict[str, int]] = {}
    for m in matches:
        p = m.get("partner")
        if not p:
            continue
        row = agg.setdefault(str(p), {"matches": 0, "wins": 0})
        row["matches"] += 1
        if m.get("won"):
            row["wins"] += 1
    rows = [{"partner": k, "matches": v["matches"], "wins": v["wins"]} for k, v in agg.items()]
    rows.sort(key=lambda r: r["matches"], reverse=True)
    return rows


def normalize(raw: Any, name: str, url: Optional[str] = None,
              source: Optional[str] = None) -> Dict[str, Any]:
    """Zet willekeurige scraper-output om naar het standaardschema."""
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        raw = {}

    history = _normalize_history(_pick(raw, [
        "ranking_history", "rankings", "klassement_historiek", "ranking_historiek",
        "ranking_snapshots", "history", "historiek"], default=[]))

    matches = _normalize_matches(_pick(raw, [
        "matches", "wedstrijden", "results", "uitslagen", "match_history"], default=[]))

    current = _rank_str(_pick(raw, ["current_ranking", "ranking", "klassement",
                                    "huidig_klassement", "rank"]))
    if not current and history:
        current = history[-1]["ranking"]

    best = _rank_str(_pick(raw, ["best_ranking", "highest_ranking",
                                 "beste_klassement", "peak_ranking"]))
    best_date = _date_str(_pick(raw, ["best_ranking_date", "highest_ranking_date",
                                      "beste_klassement_datum"]))
    if history:
        strongest = min(history, key=lambda h: rank_value(h["ranking"]) or 9999)
        if not best or (rank_value(strongest["ranking"]) or 9999) < (rank_value(best) or 9999):
            best = strongest["ranking"]
            best_date = strongest["date"]

    partners = _pick(raw, ["partners", "partner_stats"], default=None)
    if not partners:
        partners = _derive_partners(matches)

    player_id = str(_pick(raw, ["player_id", "id", "speler_id", "tvl_id", "lidnummer"])
                    or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))

    return {
        "player_id": player_id,
        "name": _pick(raw, ["name", "full_name", "player_name", "naam"]) or name,
        "profile_url": _pick(raw, ["profile_url", "url", "link"]) or url,
        "current_ranking": current,
        "best_ranking": best,
        "best_ranking_date": best_date,
        "ranking_history": history,
        "matches": matches,
        "partners": partners,
        "last_scraped": _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "scrape_source": source or "unknown",
        "raw_keys": sorted(list(raw.keys()))[:40],
    }


# ---------------------------------------------------------------------------
# Publieke scrape
# ---------------------------------------------------------------------------

class ScraperNotFound(RuntimeError):
    pass


def scrape_player(name: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Scrape 1 speler en geef genormaliseerde data terug."""
    fn, label = find_scraper()
    if fn is None:
        raise ScraperNotFound(
            "Geen spelerscraper gevonden. Voeg de juiste module/functie toe aan "
            "EXPLICIT_CANDIDATES bovenaan player_scrape_adapter.py."
        )
    raw = _call_scraper(fn, name, url)
    return normalize(raw, name=name, url=url, source=label)
