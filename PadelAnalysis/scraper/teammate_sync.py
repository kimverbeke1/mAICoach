"""
teammate_sync.py - zoekt teamgenoten waarvan het matchdocument een RECENTE
interclub-ontmoeting mist die wel in het document van een medespeler staat,
zodat de scrape-workflow ze automatisch mee kan verversen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAMMATE_SYNC_2026-10-10 (op verzoek van Kim: "ik kan Stijn en
Joris opnieuw scrapen maar als dat altijd manueel moet gebeuren dan klopt
er iets niet. Dan moet dat toch ergens in 1 van de stappen automatisch
toegevoegd worden bij bvb 'schema nu verversen'")
--------------------------------------------------------------------------
PROBLEEM: de knop "Schema nu verversen" (en elke gerichte verversing) start
scrape-padel.yml met enkel de geselecteerde speler. ci_scrape_all.py
scrapete dan enkel die speler. Zijn teamgenoten (Stijn, Joris, Nico) niet
via de nachtelijke run bijgewerkt, dan ontbreekt hun kant van de ontmoeting
en toont de Nabeschouwing te weinig matchen.
OPLOSSING (deze module, aangeroepen door ci_scrape_all.py na de
matchdata-scrape):
  1. Voor elke gescrapete speler: neem de interclub-matchen van de laatste
     N dagen (standaard 21) met een match_id en een partner_user_id.
  2. Heeft het document van die PARTNER geen matchrecord met datzelfde
     match_id, dan is de partner "verouderd" voor die ontmoeting.
  3. Verouderde partners MET een bestaand profiel worden ook gescrapet
     (geen nieuwe ghost-profielen: wie geen profiel heeft, wordt enkel
     gelogd).
  4. Dat herhaalt zich in rondes: eens Stijn bijgewerkt is, toont zijn
     document zijn partner Nico, enz. Begrensd door een maximum aantal
     rondes en een maximum aantal extra spelers.
Dit werkt op VERSCHILLEN in de data, niet op "nieuwe matchen deze run": ook
als de eigen speler al eerder bijgewerkt werd en er deze run niets nieuws
bijkwam, worden verouderde teamgenoten alsnog gevonden.
De module heeft geen Streamlit/Playwright nodig. Firestore-reads gaan via
injecteerbare functies (get_player/get_profile), zodat alles offline te
testen is (zie test_teammate_sync.py).
"""
import datetime as _dt
import logging
import re
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger("teammate_sync")

DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_MAX_ROUNDS = 3
DEFAULT_MAX_EXTRA = 10

_DMY = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_YMD = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


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
            d, mo, y = (int(x) for x in m.groups())
            return _dt.date(y, mo, d)
    except ValueError:
        return None
    return None


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
    for m in (doc or {}).get("matches") or []:
        if m.get("match_type") == "interclub" and str(m.get("match_id")) == mid:
            return True
    return False


def find_stale_teammates(
    frontier: Iterable[str],
    seen: Set[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    get_player: Optional[Callable[[str], dict]] = None,
    get_profile: Optional[Callable[[str], dict]] = None,
    today: Optional[_dt.date] = None,
) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
    """Geeft (kandidaten, redenen, zonder_profiel) terug.
      kandidaten    : partner-id's met een verouderd document en een profiel,
                      meest achterstallige eerst;
      redenen       : {partner_id: ["10/10/2026 <ontmoeting>", ...]};
      zonder_profiel: verouderde partners zonder profiel (worden NIET gescrapet).
    `seen` = spelers die al verwerkt zijn (nooit opnieuw voorgesteld)."""
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

    reasons: Dict[str, Dict[str, str]] = {}
    for pid in frontier:
        pid = str(pid)
        for m in _doc(pid).get("matches") or []:
            if m.get("match_type") != "interclub":
                continue
            mid, partner = m.get("match_id"), m.get("partner_user_id")
            if not mid or not partner or not _is_recent(m, lookback_days, today):
                continue
            partner = str(partner)
            if partner == pid or partner in seen:
                continue
            if _has_match(_doc(partner), mid):
                continue
            reasons.setdefault(partner, {})[str(mid)] = f"{m.get('match_date')} {m.get('encounter')}"

    kandidaten: List[str] = []
    zonder_profiel: List[str] = []
    for partner in reasons:
        try:
            profiel = get_profile(partner)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{partner}] profiel lezen mislukt: {exc}")
            profiel = None
        (kandidaten if profiel else zonder_profiel).append(partner)
    kandidaten.sort(key=lambda p: (-len(reasons[p]), p))
    return kandidaten, {p: list(v.values()) for p, v in reasons.items()}, sorted(zonder_profiel)


def expand_teammates(
    initial_ids: Iterable[str],
    scrape_fn: Callable[[List[str]], None],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_extra: int = DEFAULT_MAX_EXTRA,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    get_player: Optional[Callable[[str], dict]] = None,
    get_profile: Optional[Callable[[str], dict]] = None,
    today: Optional[_dt.date] = None,
) -> List[str]:
    """Zoekt in rondes verouderde teamgenoten en laat `scrape_fn(ids)` ze
    scrapen. Geeft de lijst extra gescrapete spelers terug. Een speler komt
    nooit 2x aan bod (ook niet als zijn scrape niets opleverde), dus geen lussen."""
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
            get_player=get_player, get_profile=get_profile, today=today,
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
