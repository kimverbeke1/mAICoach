"""
backfill_padelstat_history.py - zet voor elke speler zonder padelstat-historiek een STARTPUNT in de historiek.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PADELSTAT_COMPARE_2026-10-11 (op verzoek van Kim: Nabeschouwing toont "nog geen historiek bijgehouden voor
deze speler" - "dat is wel noodzakelijk")
--------------------------------------------------------------------------
ACHTERGROND: firebase_service.save_padelstat_rating() bewaart sinds 03/10 naast de huidige waarde een historiek
([{"rating", "fetched_at"}]). Dat gebeurt enkel op het moment dat de padelstat van die speler ververst wordt: de EERSTE keer
wordt de reeds gekende waarde (met zijn oude meetdatum) het startpunt, daarna komt er enkel een regel bij als de rating
verandert. Spelers die sinds 03/10 niet ververst werden, hebben dus nog GEEN historiek, ook al staat er een waarde met
meetdatum. De Nabeschouwing kan dan enkel die ene waarde gebruiken.
WAT DIT SCRIPT DOET: exact wat de eerstvolgende verversing toch zou doen, maar nu voor iedereen tegelijk en ZONDER te scrapen:
voor elk padelstat-document met een rating en een meetdatum maar zonder historiek wordt history = [{rating, fetched_at}]
geschreven (de bestaande waarde met zijn ORIGINELE meetdatum). Niets wordt overschreven; documenten die al een historiek
hebben blijven ongemoeid.
WAT HET NIET KAN: waarden van voor die eerste meting terugvinden. Een wedstrijd van voor de eerste meting krijgt dus nog
steeds een benadering (de oudste meting) - maar die staat wel duidelijk als zodanig in de Nabeschouwing.
Gebruik (vanuit PadelAnalysis/):
    python backfill_padelstat_history.py                (DROOGLOOP: toont enkel wat er zou gebeuren)
    python backfill_padelstat_history.py --apply        (schrijft de startpunten weg)
    python backfill_padelstat_history.py --player 1790766
"""
import datetime as _dt
import sys
from typing import Callable, Iterable, List, Optional, Tuple


def _as_iso(value) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return None
    return str(value)


def plan_backfill(doc: dict) -> Tuple[str, Optional[list]]:
    """Beslist per padelstat-document. Geeft (status, history|None):
       "heeft_historiek" - niets te doen;
       "geen_waarde"     - geen rating: niets te doen;
       "geen_datum"      - rating zonder meetdatum: niet aan te vullen (we zouden een datum moeten verzinnen);
       "aanvullen"       - history = [{rating, fetched_at}] te schrijven."""
    doc = doc or {}
    if doc.get("history"):
        return "heeft_historiek", None
    rating = doc.get("rating")
    if rating is None:
        return "geen_waarde", None
    moment = _as_iso(doc.get("fetched_at"))
    if not moment:
        return "geen_datum", None
    return "aanvullen", [{"rating": rating, "fetched_at": moment}]


def run(
    read_docs: Callable[[], Iterable[Tuple[str, dict]]],
    write_history: Callable[[str, list], None],
    apply: bool = False,
    only_player: Optional[str] = None,
    out: Callable[[str], None] = print,
) -> dict:
    """`read_docs()` geeft (player_id, document) terug; `write_history(pid, history)` schrijft weg (enkel bij apply)."""
    teller = {"heeft_historiek": 0, "geen_waarde": 0, "geen_datum": 0, "aanvullen": 0, "geschreven": 0, "fout": 0}
    datums: dict = {}
    voorbeelden: List[str] = []
    for pid, doc in read_docs():
        pid = str(pid)
        if only_player and pid != str(only_player):
            continue
        status, history = plan_backfill(doc)
        teller[status] += 1
        if status != "aanvullen":
            continue
        dag = str(history[0]["fetched_at"])[:10]
        datums[dag] = datums.get(dag, 0) + 1
        if len(voorbeelden) < 8:
            voorbeelden.append(f"  {pid}: rating {history[0]['rating']} gemeten op {dag}")
        if apply:
            try:
                write_history(pid, history)
                teller["geschreven"] += 1
            except Exception as exc:  # noqa: BLE001
                teller["fout"] += 1
                out(f"  FOUT bij {pid}: {type(exc).__name__}: {exc}")
    out(f"Padelstat-documenten: {sum(teller[k] for k in ('heeft_historiek', 'geen_waarde', 'geen_datum', 'aanvullen'))}")
    out(f"  met historiek (ongemoeid)        : {teller['heeft_historiek']}")
    out(f"  zonder rating (niets te doen)    : {teller['geen_waarde']}")
    out(f"  rating zonder meetdatum (overgeslagen): {teller['geen_datum']}")
    out(f"  startpunt aan te vullen          : {teller['aanvullen']}")
    if voorbeelden:
        out("Voorbeelden:")
        for v in voorbeelden:
            out(v)
        out("Meetdatums van de aan te vullen waarden (aantal per dag):")
        for dag in sorted(datums):
            out(f"  {dag}: {datums[dag]}")
    if apply:
        out(f"Weggeschreven: {teller['geschreven']} (fouten: {teller['fout']})")
    elif teller["aanvullen"]:
        out("\nDit was een DROOGLOOP - er is niets weggeschreven. Draai opnieuw met --apply om de startpunten te schrijven.")
    return teller


def main(argv: list) -> int:
    apply = "--apply" in argv
    speler = None
    if "--player" in argv:
        i = argv.index("--player")
        if i + 1 < len(argv):
            speler = argv[i + 1]
    try:
        import firebase_service as fb
    except Exception as exc:  # noqa: BLE001
        print(f"FOUT: kon firebase_service.py niet importeren: {type(exc).__name__}: {exc}")
        return 1
    col = fb.db.collection(fb.PADELSTAT_CACHE_COLLECTION)

    def read_docs():
        for d in col.stream():
            yield d.id, (d.to_dict() or {})

    def write_history(pid, history):
        col.document(str(pid)).set({"history": history}, merge=True)

    run(read_docs, write_history, apply=apply, only_player=speler)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
