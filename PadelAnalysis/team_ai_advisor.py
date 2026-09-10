"""
team_ai_advisor.py - AI-vragen, automatische inzichten en opstellingsadvies
over een tegenploeg-analyse (v4).

Ongewijzigd t.o.v. v3, behalve dat de context-tekst nu meegaat met de
klassement-richtingfix uit opponent_dossier.py: hoger getal = beter. Dit
bestand doet zelf geen berekeningen op ranggetallen, enkel weergave, dus er
was hier zelf geen bug - maar de systeeminstructie is verduidelijkt zodat het
taalmodel niet per ongeluk aanneemt dat een lager getal beter is.

Vereist een OpenAI API-key. Zoekt in deze volgorde:
  1. st.secrets["openai"]["api_key"]   (Streamlit secrets, lokaal of cloud)
  2. omgevingsvariabele OPENAI_API_KEY
Zonder geldige key geeft elke functie een duidelijke RuntimeError i.p.v. een
onduidelijke crash dieper in de OpenAI-library.
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
        "Klassement: HOE HOGER HET GETAL, HOE STERKER DE SPELER "
        "(bv. P450 is sterker dan P200).",
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

        # Laag 1: huidige poule
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

        # Laag 2: historiek
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
    aangeduide opstelling) een opstelling voor."""
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
