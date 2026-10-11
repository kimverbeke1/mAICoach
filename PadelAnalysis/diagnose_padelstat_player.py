"""
diagnose_padelstat_player.py - toont stap voor stap WAAROM een speler op padelstats.be wel of niet gevonden wordt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_NAME_MATCH_2026-10-11 (op verzoek van Kim: log "Anneleen Gallant -> niet gevonden op padelstats.be",
terwijl ze op padelstats als "Gallant Anneleen" staat)
--------------------------------------------------------------------------
De log van de achtergronddienst zegt enkel "niet gevonden", voor drie verschillende situaties:
  1. de zoekactie levert geen enkel resultaat op;
  2. ze levert wel resultaten op, maar niet de juiste speler (andere naam of andere club);
  3. de speler is gevonden, maar zijn profiel toont geen playing strength.
Dit script draait dezelfde zoekacties LIVE op jouw machine (Playwright staat er lokaal) en toont per stap wat padelstats
teruggeeft, zodat je meteen ziet welke situatie het is. Het schrijft NIETS weg (geen Firestore, geen profielen).

Gebruik (vanuit PadelAnalysis/):
    python diagnose_padelstat_player.py "Anneleen Gallant" --club "Padel Factory"
    python diagnose_padelstat_player.py "Anneleen Gallant"
    python diagnose_padelstat_player.py "Anneleen Gallant" --alleen-zoeken     (sneller: slaat het profiel over)
De club is de club zoals ze in het spelersprofiel staat (Spelers -> Club/ploeg). Het rapport komt ook in
padelstat_diagnose_rapport.txt.
"""
import sys
from typing import Callable, Optional

import padelstats_scraper as ps

_REPORT_PATH = "padelstat_diagnose_rapport.txt"


def diagnose(
    name: str, club: Optional[str], alleen_zoeken: bool = False,
    search_fn: Optional[Callable] = None, full_fn: Optional[Callable] = None,
    out: Callable[[str], None] = print,
) -> dict:
    """Geeft {"conclusie": str, "per_query": [...], "resultaat": dict | None} terug. `search_fn`/`full_fn` zijn enkel voor tests."""
    search = search_fn or ps.search_padelstat_player
    full = full_fn or ps.search_and_fetch_padelstat_rating
    out(f"Naam in ons profiel : {name!r}")
    out(f"Club in ons profiel : {club!r}")
    out(f"Woorden van de naam : {ps._name_tokens(name)}")
    out("")
    per_query = []
    out("=== Stap 1: de zoekopdrachten (zoals de scraper ze doet) ===")
    for q in ps._name_query_variants(name):
        try:
            kandidaten = search(q) or []
            fout = None
        except Exception as exc:  # noqa: BLE001
            kandidaten, fout = [], f"{type(exc).__name__}: {exc}"
        out(f"\nZoeken op {q!r}: " + (f"FOUT {fout}" if fout else f"{len(kandidaten)} resultaat/resultaten"))
        rijen = []
        for c in kandidaten:
            zelfde = ps._same_person_name(name, c.get("name"))
            club_ok = bool(club) and ps._club_matches(club, c.get("club", ""))
            rijen.append({"naam": c.get("name"), "klassement": c.get("klassement"), "club": c.get("club"),
                          "exacte_naam": zelfde, "club_klopt": club_ok})
            out(
                f"   {c.get('name')!s:<28} P{c.get('klassement')!s:<5} {c.get('club')!s:<30} "
                f"naam exact: {'JA' if zelfde else 'nee':<4} club klopt: {'JA' if club_ok else ('nee' if club else '-')}"
            )
        pick, note, reden = ps._select_candidate(name, club, kandidaten)
        out("   -> de scraper kiest: " + (f"{pick.get('name')} ({pick.get('club')})" if pick else f"niemand ({reden})"))
        if note:
            out(f"   -> waarschuwing: {note}")
        per_query.append({"query": q, "fout": fout, "kandidaten": rijen, "gekozen": pick.get("name") if pick else None, "reden": reden})
        if pick is not None:
            break
    resultaat = None
    if alleen_zoeken:
        out("\n(Stap 2 overgeslagen: --alleen-zoeken)")
    else:
        out("\n=== Stap 2: de volledige opzoeking (zoeken + profiel openen + playing strength lezen) ===")
        try:
            resultaat = full(name, club=club or None)
        except Exception as exc:  # noqa: BLE001
            out(f"FOUT: {type(exc).__name__}: {exc}")
        if resultaat is None:
            out("Resultaat: NIET GEVONDEN (de scraper geeft None terug)")
        else:
            out(
                f"Resultaat: playing strength = {resultaat.get('rating')} (bron: {resultaat.get('rating_source')}), "
                f"gekoppeld aan {resultaat.get('matched_name')!r} ({resultaat.get('matched_club')!r}), "
                f"klassement P{resultaat.get('matched_klassement')}"
            )
            if resultaat.get("club_disambiguation_note"):
                out(f"Waarschuwing: {resultaat['club_disambiguation_note']}")
            snippet = (resultaat.get("raw_text_snippet") or "")[:300]
            if snippet:
                out(f"Begin van de profielpagina: {snippet}")
    conclusie = _conclusie(per_query, resultaat, alleen_zoeken)
    out("\n=== CONCLUSIE ===")
    out(conclusie)
    return {"conclusie": conclusie, "per_query": per_query, "resultaat": resultaat}


def _conclusie(per_query: list, resultaat: Optional[dict], alleen_zoeken: bool) -> str:
    if any(q["fout"] for q in per_query) and not any(q["gekozen"] for q in per_query):
        return ("De zoekactie zelf faalde (zie de FOUT hierboven) - dat is een probleem met de verbinding of de pagina van "
                "padelstats, niet met de naam.")
    if not any(q["gekozen"] for q in per_query):
        if all(len(q["kandidaten"]) == 0 for q in per_query):
            return ("Situatie 1: padelstats geeft GEEN ENKEL resultaat voor deze naam, in geen enkele volgorde. De naam is dus "
                    "niet het probleem van de volgorde: controleer of de speler op padelstats echt zo gespeld staat "
                    "(zoek hem zelf op padelstats.be), of dat de zoekfunctie hem enkel vindt onder een andere schrijfwijze.")
        return ("Situatie 2: er zijn wel resultaten, maar geen enkel met exact deze naam en een kloppende club. De scraper koppelt "
                "dan bewust niets (anders zou een andere speler zijn waarde krijgen). Vergelijk de namen en clubs hierboven.")
    if alleen_zoeken:
        return "De speler wordt gevonden (zie hierboven). Draai zonder --alleen-zoeken om ook het profiel te controleren."
    if resultaat is None:
        return "De speler werd in stap 1 gekozen, maar de volledige opzoeking vond niets - draai het script opnieuw (mogelijk een tijdelijke fout)."
    if resultaat.get("rating") is None:
        bron = resultaat.get("rating_source")
        if bron == "click_failed":
            return "Situatie 3a: de speler is gevonden, maar het profiel kon niet geopend worden (klik op de kaart mislukt)."
        return ("Situatie 3b: de speler is gevonden en het profiel opent, maar er staat geen playing strength op. Dat geeft ook "
                "'niet gevonden' in de log. Open het profiel op padelstats.be om te zien of er een waarde staat.")
    gelijk = ps._same_person_name(per_query[-1]["gekozen"] or "", resultaat.get("matched_name") or "")
    if len(per_query) > 1 and gelijk:
        return (f"De speler wordt gevonden, maar pas bij de zoekopdracht {per_query[-1]['query']!r}. De oorspronkelijke "
                "volgorde gaf niets - dit script lost dat nu op (de scraper probeert de varianten voortaan zelf).")
    return "Alles in orde: de speler wordt gevonden en heeft een playing strength."


def main(argv: list) -> int:
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 1
    name = argv[0]
    club = None
    if "--club" in argv:
        i = argv.index("--club")
        club = argv[i + 1] if i + 1 < len(argv) else None
    regels: list = []

    def out(t: str) -> None:
        print(t)
        regels.append(t)

    diagnose(name, club, alleen_zoeken="--alleen-zoeken" in argv, out=out)
    with open(_REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(regels))
    print(f"\n>>> Rapport weggeschreven naar: {_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
