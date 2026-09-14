"""
team_ai_advisor.py - AI-vragen, automatische inzichten over een
tegenploeg-analyse, en pro/contra-commentaar op berekende opstelling-opties.

Ongewijzigd t.o.v. v7 wat betreft generate_insights/ask_about_team.

PADEL_ANALYSIS_LINEUP_OPTIONS_AI_2026-09-13 (nieuw):
Nieuwe functie analyze_lineup_options(): geeft AI-commentaar (pro's en
contra's, in het Nederlands) op de top-N BEREKENDE opstelling-opties uit
lineup_lab.optimize_lineup_vs_scenario (via dashboard.py's Opstelling-
scenario's-blok). Dit vervangt de vroegere, vrij-tekst-gebaseerde
suggest_lineup()-aanroep (die werkte op een handmatig ingevulde "onze
opstelling"-tekst, ondertussen verwijderd - zie opponent_analysis.py v8):
in plaats van de AI zelf een opstelling te laten VERZINNEN, krijgt de AI nu
de reeds EXACT BEREKENDE, cijfermatig onderbouwde opties (koppels, synergie,
matchup-edge, playing strength) en wordt gevraagd die te DUIDEN - sterke en
zwakke punten per optie, in mensentaal, zonder zelf spelers of cijfers te
verzinnen. suggest_lineup() blijft bestaan voor eventueel ander gebruik,
maar wordt niet langer aangeroepen vanuit opponent_analysis.py.
"""
from __future__ import annotations

import os
from typing import Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover - buiten Streamlit-context
    st = None

MODEL = "gpt-5-mini"


def _get_api_key() -> Optional[str]:
    if st is not None:
        try:
            openai_secrets = st.secrets.get("openai", {})
            key = openai_secrets.get("api_key") if hasattr(openai_secrets, "get") else None
            if key:
                return key
        except Exception:
            pass
    return os.environ.get("OPENAI_API_KEY")


def _client():
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "Geen OpenAI API-key gevonden. Voeg toe aan .streamlit/secrets.toml:\n"
            '[openai]\napi_key = "sk-..."\n'
            "of stel de omgevingsvariabele OPENAI_API_KEY in."
        )
    from openai import OpenAI  # lazy import: enkel nodig bij een effectieve vraag
    return OpenAI(api_key=api_key)


def _report_to_context(report: dict) -> str:
    """Zet een team-scoutingrapport (zie opponent_analysis.py) om naar platte
    tekst voor het taalmodel. Toont de twee lagen strikt gescheiden."""
    lines = [
        f"Tegenploeg: {report.get('opponent_name', '?')}",
        f"Huidige poule (spelgroep-ID): {report.get('spelgroep_id') or 'onbekend'}",
        "",
        "BELANGRIJK: 'deze poule' = de lopende competitieperiode. "
        "'historiek' = vorige periodes/andere poules, enkel bruikbaar als "
        "niveau-inschatting. Vermeng deze twee niet in je antwoord. "
        "Klassement/playing strength: HOE HOGER HET GETAL, HOE STERKER DE "
        "SPELER (bv. P450 is sterker dan P200).",
        "",
    ]

    for player in report.get("players", []) or []:
        current = player.get("current_rank")
        best = player.get("best_rank")
        lines.append(
            f"- {player.get('name', '?')}: huidig klassement "
            f"{'P' + str(current) if current is not None else 'onbekend'}, "
            f"beste ooit {'P' + str(best) if best is not None else 'onbekend'} "
            f"({player.get('best_rank_when') or 'datum onbekend'})"
        )

        n_now = player.get("matches_relevant", 0)
        if n_now:
            lines.append(
                f"  DEZE POULE: {n_now} matchen, "
                f"{player.get('wins_relevant', 0)}W-{player.get('losses_relevant', 0)}V, "
                f"winrate {player.get('winrate_relevant', '-')}"
            )
            partners = player.get("partners") or []
            if partners:
                top = ", ".join(
                    f"{row.get('Partner')} ({row.get('Matches')}x samen, winrate {row.get('Winrate')})"
                    for row in partners[:3]
                )
                lines.append(f"    Partners deze poule: {top}")
            results = player.get("poule_results") or []
            if results:
                recent = "; ".join(
                    f"{row.get('Datum')} {row.get('W/V')} vs {row.get('Tegen')} ({row.get('Score')})"
                    for row in results[:5]
                )
                lines.append(f"    Resultaten deze poule: {recent}")
        else:
            lines.append("  DEZE POULE: nog geen gespeelde matchen gekend.")

        n_hist = player.get("matches_history", 0)
        if n_hist:
            lines.append(
                f"  HISTORIEK (vorige periodes): {n_hist} matchen, "
                f"{player.get('wins_history', 0)}W-{player.get('losses_history', 0)}V, "
                f"winrate {player.get('winrate_history', '-')}, "
                f"recente vorm {player.get('form_history', '-')}"
            )
            partners_hist = player.get("partners_history") or []
            if partners_hist:
                top = ", ".join(
                    f"{row.get('Partner')} ({row.get('Matches')}x samen, winrate {row.get('Winrate')})"
                    for row in partners_hist[:3]
                )
                lines.append(f"    Vaste partners in vorige periodes: {top}")
            periods = player.get("history_periods") or []
            if periods:
                summary = "; ".join(
                    f"{row.get('Periode')}: {row.get('Matches')} matchen, winrate {row.get('Winrate')}"
                    for row in periods[:3]
                )
                lines.append(f"    Per periode: {summary}")
        else:
            lines.append("  HISTORIEK: geen eerdere interclubmatches gekend.")

    return "\n".join(lines)


_BASE_RULES = (
    "Antwoord in het Nederlands, uitsluitend op basis van de gegeven data. "
    "Maak altijd een duidelijk onderscheid tussen resultaten in de huidige poule "
    "en historiek uit vorige periodes. Onthoud dat een HOGER klassementsgetal "
    "STERKER is. Als een winrate op minder dan 3 matchen berust, benoem die dan "
    "expliciet als onbetrouwbaar. Vermeld wat onbekend is in plaats van te verzinnen."
)


def generate_insights(report: dict) -> str:
    """Genereert automatisch scoutinginzichten over de tegenploeg."""
    context = _report_to_context(report)
    client = _client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een padel-scoutingassistent. Geef een kort, scanbaar overzicht "
                    "met de belangrijkste inzichten over deze tegenploeg: wie is het sterkst, "
                    "welk dubbel komt het vaakst terug, wie gaat vooruit of achteruit qua "
                    "klassement, en welk patroon valt op in hun resultaten. Als de huidige "
                    "poule nog weinig data bevat, baseer je inschatting dan op de historiek "
                    "en zeg dat er expliciet bij. " + _BASE_RULES
                ),
            },
            {"role": "user", "content": f"Data over de tegenploeg:\n{context}"},
        ],
    )
    return response.choices[0].message.content.strip()


def ask_about_team(question: str, report: dict) -> str:
    """Beantwoordt een vrije vraag over de tegenploeg op basis van het rapport."""
    context = _report_to_context(report)
    client = _client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een padel-scoutingassistent. Antwoord kort en concreet. "
                    + _BASE_RULES
                ),
            },
            {
                "role": "user",
                "content": f"Data over de tegenploeg:\n{context}\n\nVraag: {question}",
            },
        ],
    )
    return response.choices[0].message.content.strip()


def suggest_lineup(report: dict, own_team_context: Optional[str] = None) -> str:
    """Stelt op basis van de tegenploeg-data (en optioneel onze eigen
    aangeduide opstelling) een opstelling voor.

    Behouden voor eventueel ander gebruik; wordt sinds v8 niet meer
    aangeroepen vanuit opponent_analysis.py (zie module-docstring) - gebruik
    voor de Opstelling-scenario's-pagina bij voorkeur
    analyze_lineup_options() hieronder, die op REEDS BEREKENDE opties werkt
    i.p.v. de AI zelf een opstelling te laten verzinnen."""
    context = _report_to_context(report)
    client = _client()

    if own_team_context and own_team_context.strip():
        own_part = f"\n\nOnze voorlopig aangeduide opstelling:\n{own_team_context.strip()}"
    else:
        own_part = (
            "\n\n(Geen eigen opstelling meegegeven. Baseer je enkel op de tegenploeg en "
            "vermeld expliciet dat een concreet voorstel preciezer wordt met onze eigen "
            "beschikbare spelers.)"
        )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een padel-coach die opstellingsadvies geeft voor een "
                    "interclubontmoeting. Spreek over 'dubbel 1', 'dubbel 2', enzovoort - "
                    "nooit over 'board'. Als er een voorlopige eigen opstelling is "
                    "meegegeven, beoordeel die expliciet per dubbel (wie tegen wie, en of "
                    "die matchup gunstig lijkt) en stel eventueel een wijziging voor met "
                    "motivatie. Verzin geen spelers of resultaten. " + _BASE_RULES
                ),
            },
            {"role": "user", "content": f"Data over de tegenploeg:\n{context}{own_part}"},
        ],
    )
    return response.choices[0].message.content.strip()


def _lineup_options_to_context(options: list[dict], name_lookup: dict) -> str:
    """Zet een lijst berekende opstelling-opties (zoals teruggegeven door
    lineup_lab.optimize_lineup_vs_scenario) om naar platte tekst voor het
    taalmodel. Elke optie bevat exacte koppels, synergie-scores en
    matchup-edges - de AI wordt gevraagd dit te DUIDEN, niet te herberekenen
    of te verzinnen."""
    lines = []
    for i, option in enumerate(options, start=1):
        lines.append(f"Optie {i} (totaalscore {option.get('total_score')}):")
        for a in option.get("assignment", []):
            p1, p2 = a["our_pair"]
            n1 = name_lookup.get(p1, p1)
            n2 = name_lookup.get(p2, p2)
            opp_names = " / ".join(
                p.get("name", "?") for p in a["opponent_board"].get("opponent_pair", [])
            )
            lines.append(
                f"  Dubbel: {n1} / {n2} (synergie {a['synergy']}) "
                f"tegen {opp_names or 'onbekende tegenstanders'} (matchup-edge {a['edge']:+.2f})"
            )
        lines.append("")
    return "\n".join(lines)


def analyze_lineup_options(
    report: dict,
    options: list[dict],
    name_lookup: dict,
) -> str:
    """PADEL_ANALYSIS_LINEUP_OPTIONS_AI_2026-09-13:
    Geeft AI-commentaar (pro's en contra's per optie, in het Nederlands) op
    de top-N REEDS BEREKENDE opstelling-opties uit
    lineup_lab.optimize_lineup_vs_scenario(). De AI verzint GEEN cijfers of
    spelers - ze duidt enkel de al gegeven synergie-scores, matchup-edges en
    playing-strength-gegevens uit het rapport.

    report:      het team-scoutingrapport (zie opponent_analysis.py), voor
                 context over de tegenploeg.
    options:     lijst van opstelling-opties zoals teruggegeven door
                 lineup_lab.optimize_lineup_vs_scenario (elk met
                 "total_score" en "assignment").
    name_lookup: {player_id: weergavenaam} voor ONZE eigen spelers, om de
                 ID's in de opties leesbaar te maken.
    """
    if not options:
        return "Geen berekende opstelling-opties beschikbaar om te analyseren."

    team_context = _report_to_context(report)
    options_context = _lineup_options_to_context(options, name_lookup)
    client = _client()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een padel-coach. Je krijgt een aantal AL BEREKENDE "
                    "opstelling-opties voor onze eigen ploeg tegen een specifieke "
                    "tegenstander (elke optie = een volledige verdeling van onze spelers "
                    "in dubbels, met wie tegen welk tegenstanderskoppel uitkomt). Geef PER "
                    "OPTIE een kort, concreet commentaar: wat zijn de sterke punten "
                    "(gunstige matchups, goede synergie) en de risico's (moeilijke "
                    "matchups, weinig gezamenlijke ervaring)? Sluit af met een korte "
                    "aanbeveling welke optie je zou kiezen en waarom. Spreek over 'dubbel "
                    "1', 'dubbel 2', enzovoort - nooit over 'board'. Verzin GEEN spelers, "
                    "cijfers of resultaten die niet letterlijk gegeven zijn - de "
                    "synergie-scores en matchup-edges in de data zijn al berekend, jij "
                    "duidt ze enkel. " + _BASE_RULES
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Data over de tegenploeg:\n{team_context}\n\n"
                    f"Berekende opstelling-opties:\n{options_context}"
                ),
            },
        ],
    )
    return response.choices[0].message.content.strip()
