"""
apply_sandbox_overlap_fix.py - blokkeert de Sandbox-berekening zodra
dezelfde speler in Match 1 EN Match 2 van dezelfde rotatie gekozen is.

Locatie: PadelAnalysis/apply_sandbox_overlap_fix.py  (eenmalig te draaien)

PADEL_ANALYSIS_SANDBOX_OVERLAP_BLOCKS_COMPUTE_2026-09-26 (op verzoek van Kim:
"de tegenstandres match 2 wordne niet aangepast (of niet correct) want ik
kan bvb zelfde spelers van match 1 nog kiezen wat onmogelijk is aangezien
een speler nooit in 2 matchen tegelijk kan spelen")
--------------------------------------------------------------------------
BELANGRIJKE VOORGESCHIEDENIS: deze exacte klacht staat al, woordelijk, in
dit bestand als aanleiding voor PADEL_ANALYSIS_ROTATION_OPPONENT_CROSS_
FILTER_2026-09-26 - maar die fix zit UITSLUITEND in de Rotatieplanner
(_render_rotation_planner(), de dropdown-gebaseerde tegenstander-
koppelkeuze). De Sandbox (_render_lineup_sandbox()) is een VOLLEDIG APARTE
functie met een eigen implementatie (st.multiselect i.p.v. dropdowns) en
kreeg die fix nooit.

ROOT CAUSE (bevestigd, rechtstreeks in de code gelezen): in de Sandbox
staat al een overlap-DETECTIE:

    own_overlap = set(m1_own) & set(m2_own)
    opp_overlap = set(m1_opp) & set(m2_opp)
    if own_overlap:
        st.error(f"... kan niet in beide matchen tegelijk spelen.")
    if opp_overlap:
        st.error(f"... kan niet in beide matchen tegelijk spelen.")

Maar DAARNA loopt de code gewoon door en berekent ze de winkans voor
DIEZELFDE, overlappende selectie:

    for m_i, (our_sel, opp_sel) in enumerate(matches):
        if len(our_sel) != 2 or len(opp_sel) != 2:
            incomplete = True
            continue
        ...
        own_ordered_pairs.append((p1, p2))
        opp_boards.append({"opponent_pair": opp_players})

De st.error() is dus puur cosmetisch: hij verschijnt, maar blokkeert niets.
Een speler die in Match 1 EN Match 2 van dezelfde rotatie staat - fysiek
onmogelijk, zoals Kim terecht opmerkt - krijgt gewoon een winkans-percentage
te zien alsof het een geldige opstelling was.

WAAROM DIT NIET MET DEZELFDE TECHNIEK ALS DE ROTATIEPLANNER OP TE LOSSEN IS:
de Rotatieplanner-fix filtert de opties van Match 2 LIVE op basis van wat
Match 1 al koos - dat werkt omdat die selectboxen BUITEN een st.form staan
en dus bij elke wijziging meteen een volledige rerun triggeren. De Sandbox
gebruikt bewust WEL een st.form (met "Bereken sandbox" als enige submit-
knop): Streamlit batcht wijzigingen binnen een form en rerunt pas bij
submit - vooraf filteren op een "live" keuze van de andere match is daarom
hier niet mogelijk zonder de form te verwijderen, wat exact de herhaalde-
rerun-traagheid zou terugbrengen die de form net moet voorkomen.

FIX (i.p.v. voorkomen: BLOKKEREN): is er overlap in een rotatie, dan wordt
die rotatie nu behandeld als "onvolledig" - de paren worden NIET toegevoegd
aan own_ordered_pairs/opp_boards, dus er kan nooit een winkans berekend
worden voor een fysiek onmogelijke opstelling. De bestaande st.error()-
meldingen blijven staan (ze wijzen precies aan welke rotatie het probleem
heeft); de bestaande "vul voor elke match exact 2 spelers in"-melding
verschijnt er nu ook bij, als duidelijk signaal dat er nog iets te herstellen
is voor je kan doorgaan.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_sandbox_overlap_fix.py           # dry-run
    python apply_sandbox_overlap_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_SANDBOX_OVERLAP_BLOCKS_COMPUTE_2026-09-26"

OLD_BLOCK = '''            own_overlap = set(m1_own) & set(m2_own)
            opp_overlap = set(m1_opp) & set(m2_opp)
            if own_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: {', '.join(own_overlap)} kan niet in beide matchen tegelijk spelen.")
            if opp_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: tegenstander {', '.join(opp_overlap)} kan niet in beide matchen tegelijk spelen.")
            for m_i, (our_sel, opp_sel) in enumerate(matches):
                if len(our_sel) != 2 or len(opp_sel) != 2:
                    incomplete = True
                    continue
                p1, p2 = own_label_to_id[our_sel[0]], own_label_to_id[our_sel[1]]'''

NEW_BLOCK = '''            own_overlap = set(m1_own) & set(m2_own)
            opp_overlap = set(m1_opp) & set(m2_opp)
            # PADEL_ANALYSIS_SANDBOX_OVERLAP_BLOCKS_COMPUTE_2026-09-26 (op
            # verzoek van Kim: "ik kan bvb zelfde spelers van match 1 nog
            # kiezen wat onmogelijk is aangezien een speler nooit in 2
            # matchen tegelijk kan spelen"):
            # De detectie hieronder (own_overlap/opp_overlap) bestond al,
            # maar bleef PUUR COSMETISCH - de st.error() verscheen wel, maar
            # de berekening ging gewoon door met de overlappende selectie.
            # rotation_has_overlap zorgt er nu voor dat de paren van DEZE
            # rotatie NIET meer worden toegevoegd aan own_ordered_pairs/
            # opp_boards zodra er overlap is - een fysiek onmogelijke
            # opstelling kan dus nooit meer een winkans-percentage krijgen.
            rotation_has_overlap = bool(own_overlap) or bool(opp_overlap)
            if own_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: {', '.join(own_overlap)} kan niet in beide matchen tegelijk spelen.")
            if opp_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: tegenstander {', '.join(opp_overlap)} kan niet in beide matchen tegelijk spelen.")
            for m_i, (our_sel, opp_sel) in enumerate(matches):
                if len(our_sel) != 2 or len(opp_sel) != 2:
                    incomplete = True
                    continue
                if rotation_has_overlap:
                    # Overlap in deze rotatie gedetecteerd (zie hierboven) -
                    # deze match NIET meenemen in de berekening, zodat een
                    # onmogelijke dubbele inzet van een speler nooit een
                    # winkans krijgt getoond alsof het een geldige
                    # opstelling was.
                    incomplete = True
                    continue
                p1, p2 = own_label_to_id[our_sel[0]], own_label_to_id[our_sel[1]]'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_BLOCK not in tekst:
        print("  KON HET TE VERVANGEN BLOK NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  (het bestand wijkt af van wat verwacht werd; stuur het opnieuw voor controle)")
        return False

    nieuw = tekst.replace(OLD_BLOCK, NEW_BLOCK, 1)
    print("  Sandbox-overlapdetectie: klaar om de berekening effectief te blokkeren.")

    if not apply:
        print(f"\n  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"\n  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Blokkeert de Sandbox-berekening bij een overlappende speler-selectie."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="page_lineup_lab.py",
                        help="Pad naar page_lineup_lab.py (standaard: huidige map).")
    args = parser.parse_args()

    pad = Path(args.file).resolve()
    print(f"Bestand: {pad}")
    print(f"Modus: {'TOEPASSEN' if args.apply else 'DRY-RUN (er wordt niets gewijzigd)'}\n")

    gelukt = _patch(pad, args.apply)

    print()
    if not gelukt:
        print("Er is niets gewijzigd.")
        return
    if args.apply:
        check_cmd = (
            "python -c \"import ast; ast.parse(open(r'"
            + pad.name
            + "', encoding='utf-8').read()); print('OK')\""
        )
        print("Klaar. Controleer met:")
        print(f"  {check_cmd}")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
