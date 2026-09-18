"""
team_ai_advisor.py - AI-vragen, automatische inzichten over een
tegenploeg-analyse, en pro/contra-commentaar op berekende opstelling-opties.

Ongewijzigd t.o.v. v7 wat betreft de kernlogica van generate_insights.

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

--------------------------------------------------------------------------
PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18 (op verzoek van Kim: "bij de AI
functie kan je zaken intypen in een prompt en dat werkt maar je kan niet
verder doorvragen in nieuwe prompt" / "zorg dat ik kan doorvragen")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd): elke AI-aanroep (generate_insights, ask_about_team,
analyze_lineup_options) startte een VOLLEDIG NIEUWE OpenAI-conversatie
(1 system-bericht + 1 user-bericht), zonder ooit de vorige vraag/antwoord
mee te sturen. Er werd nergens conversatiegeschiedenis bijgehouden of
doorgegeven - elke nieuwe "Vraag AI"-klik was voor het taalmodel een
compleet losstaand gesprek, zonder enige herinnering aan wat er eerder
gevraagd/geantwoord was. Dat is de reden waarom "doorvragen" niet werkte:
een vervolgvraag zoals "en wat als Kim niet kan spelen?" werd behandeld als
een geheel nieuwe, contextloze vraag.

FIX: nieuwe, generieke kernfunctie _chat_completion(system_prompt,
first_user_message, history) die een messages-lijst opbouwt als
    [system] + history + [nieuwste user-bericht]
i.p.v. steeds [system, user] met NIETS ertussen. `history` is een simpele
lijst van {"role": "user"/"assistant", "content": str}-dicts, die de
AANROEPER (opponent_analysis.py / page_lineup_lab.py) bijhoudt in
st.session_state en bij ELKE nieuwe vraag volledig meestuurt - zo bouwt het
taalmodel een steeds groeiend, samenhangend gesprek op, net als een gewone
chatbot.

Alle 3 bestaande, door de UI aangeroepen functies (generate_insights,
ask_about_team, analyze_lineup_options) hebben nu een OPTIONELE
`history`-parameter (standaard None = lege lijst) - bestaande aanroepen
zonder dit argument blijven dus exact zoals voorheen werken (geen
doorvraag-geschiedenis), en zijn dus volledig achterwaarts compatibel.
Geen enkele bestaande aanroep-plek MOET aangepast worden om te blijven
werken; enkel de plekken die Kim vroeg (de "Vraag AI"-sectie) geven nu wel
hun opgebouwde geschiedenis mee.

Een 4e, nieuwe functie ask_followup(question, report, history) is een
dunne, expliciet zo genoemde wrapper rond ask_about_team() met
geschiedenis - puur voor leesbaarheid in de aanroepende UI-code.
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


def _chat_completion(system_prompt: str, user_message: str, history: Optional[list[dict]] = None) -> str:
    """PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: generieke kernfunctie die
    ALTIJD de opgebouwde `history` (eerdere user/assistant-berichten van
    ditzelfde gesprek) meestuurt vóór het nieuwste user-bericht, i.p.v. bij
    elke aanroep een volledig nieuw, contextloos gesprek te starten.

    history: lijst van {"role": "user"|"assistant", "content": str}-dicts,
    in chronologische volgorde (oudste eerst). Wordt NIET aangepast door
    deze functie - de aanroeper is verantwoordelijk voor het bijhouden en
    uitbreiden van de geschiedenis (typisch in st.session_state)."""
    client = _client()
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message})
    response = client.chat.completions.create(model=MODEL, messages=messages)
    return response.choices[0].message.content.strip()


def generate_insights(report: dict) -> str:
    """Genereert automatisch scoutinginzichten over de tegenploeg. Dit is
    altijd het STARTPUNT van een gesprek (geen voorgeschiedenis mogelijk/
    zinvol), dus zonder history-parameter."""
    context = _report_to_context(report)
    system_prompt = (
        "Je bent een padel-scoutingassistent. Geef een kort, scanbaar overzicht "
        "met de belangrijkste inzichten over deze tegenploeg: wie is het sterkst, "
        "welk dubbel komt het vaakst terug, wie gaat vooruit of achteruit qua "
        "klassement, en welk patroon valt op in hun resultaten. Als de huidige "
        "poule nog weinig data bevat, baseer je inschatting dan op de historiek "
        "en zeg dat er expliciet bij. " + _BASE_RULES
    )
    return _chat_completion(system_prompt, f"Data over de tegenploeg:\n{context}")


def ask_about_team(question: str, report: dict, history: Optional[list[dict]] = None) -> str:
    """Beantwoordt een vrije vraag over de tegenploeg op basis van het
    rapport.

    PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: heeft nu een OPTIONELE
    `history`-parameter. Wordt die meegegeven, dan bouwt het antwoord VERDER
    op het eerdere gesprek (echt doorvragen mogelijk) i.p.v. elke vraag als
    volledig nieuw, contextloos gesprek te behandelen. Achterwaarts
    compatibel: bestaande aanroepen zonder `history` werken exact als
    voorheen."""
    context = _report_to_context(report)
    system_prompt = (
        "Je bent een padel-scoutingassistent. Antwoord kort en concreet. "
        "Als dit een VERVOLGVRAAG is op een eerder antwoord in dit gesprek, "
        "bouw dan expliciet verder op wat je eerder al zei - herhaal niet "
        "onnodig dezelfde uitleg, maar verwijs ernaar of vul ze aan. "
        + _BASE_RULES
    )
    user_message = f"Data over de tegenploeg:\n{context}\n\nVraag: {question}"
    return _chat_completion(system_prompt, user_message, history=history)


def ask_followup(question: str, report: dict, history: list[dict]) -> str:
    """PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: dunne, expliciet zo
    genoemde wrapper rond ask_about_team() MET geschiedenis - puur voor
    leesbaarheid in de aanroepende UI-code (maakt op de aanroep-plek
    meteen duidelijk dat dit een doorvraag is, geen eerste vraag)."""
    return ask_about_team(question, report, history=history)


def suggest_lineup(report: dict, own_team_context: Optional[str] = None) -> str:
    """Stelt op basis van de tegenploeg-data (en optioneel onze eigen
    aangeduide opstelling) een opstelling voor.

    Behouden voor eventueel ander gebruik; wordt sinds v8 niet meer
    aangeroepen vanuit opponent_analysis.py (zie module-docstring) - gebruik
    voor de Opstelling-scenario's-pagina bij voorkeur
    analyze_lineup_options() hieronder, die op REEDS BEREKENDE opties werkt
    i.p.v. de AI zelf een opstelling te laten verzinnen."""
    context = _report_to_context(report)
    if own_team_context and own_team_context.strip():
        own_part = f"\n\nOnze voorlopig aangeduide opstelling:\n{own_team_context.strip()}"
    else:
        own_part = (
            "\n\n(Geen eigen opstelling meegegeven. Baseer je enkel op de tegenploeg en "
            "vermeld expliciet dat een concreet voorstel preciezer wordt met onze eigen "
            "beschikbare spelers.)"
        )
    system_prompt = (
        "Je bent een padel-coach die opstellingsadvies geeft voor een "
        "interclubontmoeting. Spreek over 'dubbel 1', 'dubbel 2', enzovoort - "
        "nooit over 'board'. Als er een voorlopige eigen opstelling is "
        "meegegeven, beoordeel die expliciet per dubbel (wie tegen wie, en of "
        "die matchup gunstig lijkt) en stel eventueel een wijziging voor met "
        "motivatie. Verzin geen spelers of resultaten. " + _BASE_RULES
    )
    return _chat_completion(system_prompt, f"Data over de tegenploeg:\n{context}{own_part}")


def _lineup_options_to_context(options: list[dict], name_lookup: dict) -> str:
    """Zet een lijst berekende opstelling-opties (zoals teruggegeven door
    lineup_lab.optimize_lineup_vs_scenario) om naar platte tekst voor het
    taalmodel. Elke optie bevat exacte koppels, synergie-scores en
    matchup-edges - de AI wordt gevraagd dit te DUIDEN, niet te herberekenen
    of te verzinnen."""
    lines = []
    for i, option in enumerate(options, start=1):
        header = f"Optie {i}"
        ebw = option.get("expected_boards_won")
        if ebw is not None:
            header += f" (verwacht {ebw:.2f} matchen gewonnen)"
        else:
            header += f" (totaalscore {option.get('total_score')})"
        lines.append(header + ":")
        for a in option.get("assignment", []):
            p1, p2 = a["our_pair"]
            n1 = name_lookup.get(p1, p1)
            n2 = name_lookup.get(p2, p2)
            opp_names = " / ".join(
                p.get("name", "?") for p in a["opponent_board"].get("opponent_pair", [])
            )
            wp = a.get("win_probability")
            wp_txt = f", winkans {int(round(wp*100))}%" if wp is not None else ""
            lines.append(
                f"  Dubbel: {n1} / {n2} (synergie {a['synergy']}) "
                f"tegen {opp_names or 'onbekende tegenstanders'} (matchup-edge {a['edge']:+.2f}{wp_txt})"
            )
        lines.append("")
    return "\n".join(lines)


def analyze_lineup_options(
    report: dict,
    options: list[dict],
    name_lookup: dict,
    history: Optional[list[dict]] = None,
) -> str:
    """PADEL_ANALYSIS_LINEUP_OPTIONS_AI_2026-09-13, uitgebreid in
    PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18 met een optionele
    `history`-parameter (zelfde achterwaarts-compatibele patroon als
    ask_about_team hierboven).

    Geeft AI-commentaar (pro's en contra's per optie, in het Nederlands) op
    de top-N REEDS BEREKENDE opstelling-opties uit
    lineup_lab.optimize_lineup_vs_scenario(). De AI verzint GEEN cijfers of
    spelers - ze duidt enkel de al gegeven synergie-scores, matchup-edges en
    playing-strength-gegevens uit het rapport.

    report:      het team-scoutingrapport (zie opponent_analysis.py), voor
                 context over de tegenploeg.
    options:     lijst van opstelling-opties zoals teruggegeven door
                 lineup_lab.optimize_lineup_vs_scenario (elk met
                 "total_score"/"expected_boards_won" en "assignment").
    name_lookup: {player_id: weergavenaam} voor ONZE eigen spelers, om de
                 ID's in de opties leesbaar te maken.
    history:     optioneel, eerdere {"role":..,"content":..}-berichten van
                 hetzelfde gesprek (voor doorvragen na het eerste antwoord).
    """
    if not options:
        return "Geen berekende opstelling-opties beschikbaar om te analyseren."
    team_context = _report_to_context(report)
    options_context = _lineup_options_to_context(options, name_lookup)
    system_prompt = (
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
        "duidt ze enkel. Als dit een VERVOLGVRAAG is op een eerder antwoord in "
        "dit gesprek, bouw daar dan expliciet op voort. " + _BASE_RULES
    )
    user_message = (
        f"Data over de tegenploeg:\n{team_context}\n\n"
        f"Berekende opstelling-opties:\n{options_context}"
    )
    return _chat_completion(system_prompt, user_message, history=history)
