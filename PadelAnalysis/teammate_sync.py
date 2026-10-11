"""
teammate_sync.py - zoekt teamgenoten waarvan het matchdocument een RECENTE
interclub-ontmoeting mist, zodat de scrape-workflow (en de Nabeschouwing) ze
automatisch kan verversen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAMMATE_SYNC_2026-10-10 (op verzoek van Kim: "ik kan Stijn en
Joris opnieuw scrapen maar als dat altijd manueel moet gebeuren dan klopt
er iets niet")
--------------------------------------------------------------------------
PROBLEEM: de knop "Schema nu verversen" start scrape-padel.yml met enkel de
geselecteerde speler. Teamgenoten waarvan het document de recente ontmoeting
nog niet bevat, ontbreken dan in de Nabeschouwing.
REGEL 1 (PARTNER-KETEN): voor elke gescrapete speler worden de interclub-
matchen van de laatste N dagen bekeken (match_id + partner_user_id). Heeft het
document van die PARTNER geen record met dat match_id, dan is de partner
"verouderd" en wordt ook die gescrapet; in rondes (Stijn + Joris, daarna Nico).
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAMMATE_ROSTER_2026-10-11 (op verzoek van Kim: Nabeschouwing toonde
bij een lopende ontmoeting (enkel rotatie 1 gespeeld) maar 1 van de 2 matchen van
rotatie 1, ondanks "schema verversen")
--------------------------------------------------------------------------
ROOT CAUSE: regel 1 loopt enkel via PARTNERS. Bij een lopende ontmoeting speelt
een ander koppel (Y/Z) rotatie 1 zonder dat een van hen met de gescrapete speler
(of diens partner) samenspeelde: de keten bereikt hen nooit. De Nabeschouwing
zag dus enkel de eigen match.
REGEL 2 (PLOEG-ROSTER): de ploegleden zijn te vinden via de partnerrelaties in
DEZELFDE reeks (spelgroepId, uit de uitslagenblad-link van de matchen): wie in
die reeks met iemand van de ploeg speelde, hoort bij de ploeg (breadth-first,
begrensd). Een ploeglid is "verouderd" voor een ontmoeting als zijn document die
ontmoeting (zelfde datum + ontmoeting-tekst) NIET bevat EN zijn document niet
NA de ontmoeting bijgewerkt is. Is het document wel recenter bijgewerkt en
ontbreekt de ontmoeting, dan speelde hij niet mee: hij wordt niet opnieuw gescrapet.
Is de bijwerkdatum niet te bepalen (onbekend veld), dan telt hij als verouderd.
Dezelfde functies worden gebruikt door de scrape-workflow (ci_scrape_all.py ->
expand_teammates()) en door de Nabeschouwing (retro_refresh.py, knop "Teamgenoten
bijwerken").
Enkel spelers MET een bestaand profiel worden meegenomen - geen nieuwe
ghost-profielen; wie geen profiel heeft, wordt enkel gelogd/getoond.
De module heeft geen Streamlit/Playwright nodig. Firestore-reads gaan via
injecteerbare functies (get_player/get_profile), zodat alles offline te testen is
(zie test_teammate_sync.py en test_teammate_roster.py).
Env (optioneel): TEAMMATE_ROSTER_RULE=false zet regel 2 uit in de workflow.
"""
import datetime as _dt
import logging
import os
import re
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("teammate_sync")

DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_MAX_ROUNDS = 3
DEFAULT_MAX_EXTRA = 10
DEFAULT_ROSTER_MAX_NODES = 40

_DMY = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:\D+(\d{1,2}):(\d{2}))?")
_YMD = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
# Velden waarin een spelersdocument de datum van de laatste scrape kan bewaren (de exacte naam is
# niet gecontroleerd; test_teammate_roster.py --live <id> toont welke aanwezig is).
_DOC_TIMESTAMP_KEYS = (
    "scraped_at", "last_scraped_at", "last_scraped", "last_updated", "updated_at", "last_refresh",
    "last_refreshed", "fetched_at", "scraped", "last_update",
)


def parse_match_date(text) -> Optional[_dt.date]:
    """"10/10/2026", "10-10-2026 09:30" of "2026-10-10" -> date, anders None."""
    if not text:
        return None
    s = str(text).strip()
    m = _YMD.match(s)
    try:
        if m:
            y, mo, d = (int(x) for x in m.groups())
            return _dt.date(y, mo, d)
        m = _DMY.search(s)
        if m:
            d, mo, y = (int(x) for x in m.groups()[:3])
            return _dt.date(y, mo, d)
    except ValueError:
        return None
    return None


def _to_date(value) -> Optional[_dt.date]:
    """datetime/date/ISO-tekst/epoch (s of ms) -> date, anders None."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v > 1e12:
            v /= 1000.0
        try:
            return _dt.datetime.fromtimestamp(v, _dt.timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    if hasattr(value, "isoformat") and hasattr(value, "year"):
        try:
            return _dt.date(value.year, value.month, value.day)
        except Exception:  # noqa: BLE001
            return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return parse_match_date(s)


def doc_timestamp(doc: dict) -> Optional[_dt.date]:
    """Datum van de laatste scrape van dit spelersdocument, of None als dat niet te bepalen is."""
    if not isinstance(doc, dict):
        return None
    for key in _DOC_TIMESTAMP_KEYS:
        d = _to_date(doc.get(key))
        if d is not None:
            return d
    return None


def series_key(m: dict) -> str:
    """Reeks/poule-sleutel van 1 matchrecord: spelgroepId (veld of uit de uitslagenblad-link), anders de reeksnaam."""
    sid = m.get("spelgroep_id")
    if not sid:
        url = m.get("uitslagenblad_url") or ""
        try:
            sid = (parse_qs(urlparse(str(url)).query).get("spelgroepId") or [None])[0]
        except Exception:  # noqa: BLE001
            sid = None
    return str(sid) if sid else str(m.get("reeks_name") or "")


def encounter_key(m: dict) -> tuple:
    """Zelfde sleutel als lineup_retrospective._encounter_key(): (datum-tekst, ontmoeting-tekst)."""
    return (m.get("match_date") or "", m.get("encounter") or "")


def _interclub(doc: dict) -> list:
    return [m for m in (doc or {}).get("matches") or [] if m.get("match_type") == "interclub"]


def has_encounter(doc: dict, enc_key: tuple) -> bool:
    return any(encounter_key(m) == enc_key for m in _interclub(doc))


def _default_get_player(pid: str) -> dict:
    import firebase_service as fb
    return fb.get_player(pid) or {}


def _default_get_profile(pid: str) -> dict:
    import firebase_service as fb
    return fb.get_player_profile(pid) or {}


def _is_recent(match: dict, lookback_days: int, today: _dt.date) -> bool:
    d = parse_match_date(match.get("match_date"))
    if d is None:
        return False
    return today - _dt.timedelta(days=lookback_days) <= d <= today + _dt.timedelta(days=1)


def _has_match(doc: dict, match_id) -> bool:
    mid = str(match_id)
    for m in _interclub(doc):
        if str(m.get("match_id")) == mid:
            return True
    return False


# ----------------------------------------------------------------------------- regel 2: ploeg-roster
def collect_roster(
    seed: str, get_doc: Callable[[str], dict], series_keys: Set[str], max_nodes: int = DEFAULT_ROSTER_MAX_NODES,
    only_encounter: Optional[tuple] = None,
) -> Tuple[Set[str], Dict[str, dict]]:
    """Breadth-first over de partnerrelaties in de gegeven reeks(en), vanaf `seed`. Geeft (roster, docs) terug, met
    docs = {speler: document} van alle bezochte spelers. Begrensd op `max_nodes` spelers.
    Is er GEEN reeks bekend (`series_keys` leeg), dan blijft het roster bewust klein: enkel partnerschappen in de ene
    ontmoeting `only_encounter` tellen mee (liever te weinig dan een lek naar andere ploegen)."""
    seed = str(seed)
    roster: Set[str] = {seed}
    docs: Dict[str, dict] = {}
    queue = [seed]
    while queue:
        cur = queue.pop(0)
        try:
            doc = get_doc(cur) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{cur}] document lezen mislukt: {exc}")
            doc = {}
        docs[cur] = doc
        for m in _interclub(doc):
            if series_keys:
                if series_key(m) not in series_keys:
                    continue
            elif only_encounter is not None and encounter_key(m) != only_encounter:
                continue
            elif only_encounter is None:
                continue
            partner = m.get("partner_user_id")
            if not partner:
                continue
            partner = str(partner)
            if partner not in roster and len(roster) < max_nodes:
                roster.add(partner)
                queue.append(partner)
    return roster, docs


def classify_roster(
    sel_id: str, enc_key: tuple, roster: Iterable[str], docs: Dict[str, dict],
    profile_ids: Optional[Set[str]] = None,
) -> dict:
    """Deelt de ploegleden (behalve `sel_id`) in voor ontmoeting `enc_key`:
      have          : hun document bevat de ontmoeting al;
      stale         : ontmoeting ontbreekt EN document niet na de ontmoeting bijgewerkt (of datum onbekend) -> bijwerken;
      fresh_without : ontmoeting ontbreekt maar document is NA de ontmoeting bijgewerkt -> speelde niet mee;
      no_profile    : ontmoeting ontbreekt en er is geen profiel (kan niet gescrapet worden)."""
    enc_date = parse_match_date(enc_key[0])
    out = {"have": [], "stale": [], "fresh_without": [], "no_profile": []}
    for pid in sorted({str(p) for p in roster}):
        if pid == str(sel_id):
            continue
        doc = docs.get(pid)
        if doc and has_encounter(doc, enc_key):
            out["have"].append(pid)
            continue
        if profile_ids is not None and pid not in profile_ids:
            out["no_profile"].append(pid)
            continue
        ts = doc_timestamp(doc) if doc else None
        if ts is not None and enc_date is not None and ts > enc_date:
            out["fresh_without"].append(pid)
        else:
            out["stale"].append(pid)
    return out


def roster_info_for_encounter(
    sel_id: str, enc_key: tuple, docs: Dict[str, dict], profile_ids: Optional[Set[str]] = None,
) -> dict:
    """Voor de Nabeschouwing: alle documenten zijn al geladen (`docs`, incl. dat van `sel_id`). Geeft
    {"roster", "series", "have", "stale", "fresh_without", "no_profile"} terug."""
    sel_id = str(sel_id)
    docs = {str(k): v for k, v in (docs or {}).items()}
    series: Set[str] = set()
    for m in _interclub(docs.get(sel_id) or {}):
        if encounter_key(m) == enc_key:
            series.add(series_key(m))
    if not series:
        for d in docs.values():
            for m in _interclub(d):
                if encounter_key(m) == enc_key:
                    series.add(series_key(m))
    series.discard("")
    roster, _ = collect_roster(sel_id, lambda p: docs.get(p, {}), series, only_encounter=enc_key)
    info = classify_roster(sel_id, enc_key, roster, docs, profile_ids)
    info["roster"] = sorted(roster)
    info["series"] = sorted(series)
    return info


def find_roster_stale_teammates(
    frontier: Iterable[str],
    seen: Set[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    get_player: Optional[Callable[[str], dict]] = None,
    get_profile: Optional[Callable[[str], dict]] = None,
    today: Optional[_dt.date] = None,
    max_nodes: int = DEFAULT_ROSTER_MAX_NODES,
) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
    """Regel 2 voor de workflow: voor elke recente ontmoeting van de gescrapete spelers het ploeg-roster bepalen en de
    verouderde ploegleden teruggeven. Geeft (kandidaten, redenen, zonder_profiel) terug."""
    get_player = get_player or _default_get_player
    get_profile = get_profile or _default_get_profile
    today = today or _dt.date.today()
    cache: Dict[str, dict] = {}

    def _doc(pid: str) -> dict:
        if pid not in cache:
            try:
                cache[pid] = get_player(pid) or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{pid}] document lezen mislukt: {exc}")
                cache[pid] = {}
        return cache[pid]

    reasons: Dict[str, Dict[tuple, str]] = {}
    geen_profiel: Set[str] = set()
    profielen: Dict[str, bool] = {}

    def _has_profile(pid: str) -> bool:
        if pid not in profielen:
            try:
                profielen[pid] = bool(get_profile(pid))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{pid}] profiel lezen mislukt: {exc}")
                profielen[pid] = False
        return profielen[pid]

    for pid in frontier:
        pid = str(pid)
        enc_series: Dict[tuple, Set[str]] = {}
        for m in _interclub(_doc(pid)):
            if _is_recent(m, lookback_days, today):
                enc_series.setdefault(encounter_key(m), set()).add(series_key(m))
        for enc_key, series in enc_series.items():
            series.discard("")
            roster, docs = collect_roster(pid, _doc, series, max_nodes=max_nodes, only_encounter=enc_key)
            ids = {str(x) for x in roster}
            # profiel enkel opvragen voor wie de ontmoeting mist (anders onnodige reads)
            kandidaat_ids = [p for p in ids if p != pid and not (docs.get(p) and has_encounter(docs[p], enc_key))]
            pf = {p for p in kandidaat_ids if _has_profile(p)}
            info = classify_roster(pid, enc_key, ids, docs, profile_ids=pf | {p for p in ids if p not in kandidaat_ids})
            for p in info["stale"]:
                if p in seen or p == pid:
                    continue
                reasons.setdefault(p, {})[enc_key] = f"{enc_key[0]} {enc_key[1]}"
            for p in info["no_profile"]:
                if p not in seen:
                    geen_profiel.add(p)
    kandidaten = sorted(reasons, key=lambda p: (-len(reasons[p]), p))
    return kandidaten, {p: list(v.values()) for p, v in reasons.items()}, sorted(geen_profiel)


# ----------------------------------------------------------------------------- regel 1: partner-keten
def find_stale_teammates(
    frontier: Iterable[str],
    seen: Set[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    get_player: Optional[Callable[[str], dict]] = None,
    get_profile: Optional[Callable[[str], dict]] = None,
    today: Optional[_dt.date] = None,
    use_roster: Optional[bool] = None,
) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
    """Geeft (kandidaten, redenen, zonder_profiel) terug.
      kandidaten    : speler-id's met een verouderd document en een profiel, meest achterstallige eerst;
      redenen       : {speler_id: ["10/10/2026 <ontmoeting>", ...]};
      zonder_profiel: verouderde spelers zonder profiel (worden NIET gescrapet).
    `seen` = spelers die al verwerkt zijn (nooit opnieuw voorgesteld). Regel 1 (partner-keten) + regel 2 (ploeg-roster,
    uit te zetten met use_roster=False of env TEAMMATE_ROSTER_RULE=false)."""
    get_player = get_player or _default_get_player
    get_profile = get_profile or _default_get_profile
    today = today or _dt.date.today()
    frontier = [str(p) for p in frontier]
    cache: Dict[str, dict] = {}

    def _doc(pid: str) -> dict:
        if pid not in cache:
            try:
                cache[pid] = get_player(pid) or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{pid}] document lezen mislukt: {exc}")
                cache[pid] = {}
        return cache[pid]

    reasons: Dict[str, Dict[str, str]] = {}
    for pid in frontier:
        for m in _interclub(_doc(pid)):
            mid, partner = m.get("match_id"), m.get("partner_user_id")
            if not mid or not partner or not _is_recent(m, lookback_days, today):
                continue
            partner = str(partner)
            if partner == pid or partner in seen:
                continue
            if _has_match(_doc(partner), mid):
                continue
            reasons.setdefault(partner, {})[str(mid)] = f"{m.get('match_date')} {m.get('encounter')}"

    zonder_profiel: List[str] = []
    kandidaten: List[str] = []
    for partner in reasons:
        try:
            profiel = get_profile(partner)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{partner}] profiel lezen mislukt: {exc}")
            profiel = None
        (kandidaten if profiel else zonder_profiel).append(partner)

    if use_roster is None:
        use_roster = os.environ.get("TEAMMATE_ROSTER_RULE", "true").strip().lower() not in ("0", "false", "no", "off")
    redenen = {p: list(v.values()) for p, v in reasons.items()}
    if use_roster:
        # De partner-keten-spelers zitten al in `reasons`; het roster mag hen niet dubbel tellen.
        r_kand, r_redenen, r_geen = find_roster_stale_teammates(
            frontier, set(seen) | set(frontier), lookback_days, get_player=_doc, get_profile=get_profile, today=today,
        )
        for p in r_kand:
            if p not in kandidaten:
                kandidaten.append(p)
            redenen.setdefault(p, [])
            for tekst in r_redenen.get(p, []):
                if tekst not in redenen[p]:
                    redenen[p].append(tekst)
        for p in r_geen:
            if p not in zonder_profiel and p not in kandidaten:
                zonder_profiel.append(p)
    kandidaten.sort(key=lambda p: (-len(redenen.get(p, [])), p))
    return kandidaten, redenen, sorted(zonder_profiel)


def expand_teammates(
    initial_ids: Iterable[str],
    scrape_fn: Callable[[List[str]], None],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_extra: int = DEFAULT_MAX_EXTRA,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    get_player: Optional[Callable[[str], dict]] = None,
    get_profile: Optional[Callable[[str], dict]] = None,
    today: Optional[_dt.date] = None,
    use_roster: Optional[bool] = None,
) -> List[str]:
    """Zoekt in rondes verouderde teamgenoten en laat `scrape_fn(ids)` ze scrapen. Geeft de lijst extra gescrapete spelers
    terug. Een speler komt nooit 2x aan bod (ook niet als zijn scrape niets opleverde), dus geen lussen. De gelezen
    documenten worden per ronde vers opgehaald (na een scrape zijn ze veranderd)."""
    seen: Set[str] = {str(p) for p in initial_ids}
    frontier: List[str] = sorted(seen)
    extras: List[str] = []
    for ronde in range(1, max_rounds + 1):
        budget = max_extra - len(extras)
        if budget <= 0:
            logger.info(f"Teamgenoten-sync: maximum van {max_extra} extra spelers bereikt.")
            break
        kandidaten, redenen, zonder_profiel = find_stale_teammates(
            frontier, seen, lookback_days=lookback_days,
            get_player=get_player, get_profile=get_profile, today=today, use_roster=use_roster,
        )
        if zonder_profiel:
            logger.info(
                f"Teamgenoten-sync ronde {ronde}: {len(zonder_profiel)} verouderde speler(s) zonder profiel "
                f"overgeslagen (geen ghost-profielen): {', '.join(zonder_profiel)}"
            )
        if not kandidaten:
            logger.info(f"Teamgenoten-sync ronde {ronde}: geen verouderde teamgenoten gevonden.")
            break
        if len(kandidaten) > budget:
            logger.info(
                f"Teamgenoten-sync ronde {ronde}: {len(kandidaten)} kandidaten, maar nog maar budget voor {budget}."
            )
            kandidaten = kandidaten[:budget]
        for p in kandidaten:
            logger.info(f"  teamgenoot {p} mist: {'; '.join(redenen.get(p, []))}")
        scrape_fn(kandidaten)
        extras.extend(kandidaten)
        seen.update(kandidaten)
        frontier = list(kandidaten)
    return extras
