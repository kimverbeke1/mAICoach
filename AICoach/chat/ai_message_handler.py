# -*- coding: utf-8 -*-

import json

from AICoach.ai_analysis_data import build_ai_analysis_data
from AICoach.app_config import get_secret, use_real_ai
from AICoach.context_builder import build_context

# Configuratie via app_config: werkt lokaal (.env) en op Streamlit Cloud (st.secrets).
OPENAI_MODEL = get_secret("OPENAI_MODEL", "gpt-5-mini")

# Optionele wetenschappelijke grondslag. Als science_knowledge aanwezig is,
# wordt de vaste wetenschappelijke basis (Banister Fitness-Fatigue) meegegeven.
try:
    from AICoach.science_knowledge import science_system_block

    _SCIENCE_BLOCK = science_system_block()
except Exception:  # noqa: BLE001 - science_knowledge is optioneel
    _SCIENCE_BLOCK = ""

BASE_RULES = """
Je bent mAICoach, een persoonlijke sportcoach en sportdata-analist.

## INHOUDELIJKE REGELS
- Beantwoord exact de vraag in natuurlijke, vlotte Nederlandse taal.
- Geef maximaal 5 inzichten, gerangschikt op praktische waarde.
- Gebruik alleen data die werkelijk is aangeleverd en verzin niets.
- Zet cijfers, bronrecords, berekeningen, beperkingen en onzekerheden onder "### Technische details".
- Voor Running en TrailRun mag snelheid gedeeld door gemiddelde hartslag uitsluitend als praktische efficiëntie-indicatie worden gebruikt.
- Corrigeer je interpretatie voor zover mogelijk voor afstand, duur, hoogteprofiel, temperatuur, wind, trainingsdoel en wedstrijdcontext.
- Voor Padel en Badminton mag je geen betere of slechtere prestatie afleiden uit load, duur of hartslag.
- Beschrijf Padel en Badminton alleen als fysiologische belasting, herstelcontext en verloop van de sessie.
- Hogere training load betekent meer fysiologische belasting, niet automatisch betere kwaliteit.
- Gebruik de Intervals-stressparameter niet.
- Gebruik readiness alleen wanneer echte waarden aanwezig zijn en presenteer de betekenis voorzichtig.
- Behandel persoonlijke patronen als veranderlijke hypotheses.
- Samenhang bewijst geen oorzaak.
- Schrijf vriendelijk, helder en direct, zonder HTML, tabellen, geneste lijsten of consultantentaal.
- Schrijf getallen als cijfers, bijvoorbeeld -7.6, 6.2 uur en 50 bpm.
- Eindig niet met een vraag.
""".strip()


def _system_prefix() -> str:
    """Wetenschappelijke grondslag (indien beschikbaar) gevolgd door de basisregels."""
    if _SCIENCE_BLOCK:
        return f"{_SCIENCE_BLOCK}\n\n{BASE_RULES}"
    return BASE_RULES


def _run_ai(prompt: str) -> str:
    if not use_real_ai():
        return (
            "De echte AI-call staat uit. Zet `USE_REAL_AI=true` in `.env` of in "
            "Streamlit Secrets om deze analyse uit te voeren.\n\n### Technische details\n"
            "Er is geen externe AI-call uitgevoerd."
        )

    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY ontbreekt in `.env` of in Streamlit Secrets."

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
        )
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
        return "De AI gaf geen tekst terug."
    except Exception as exc:  # noqa: BLE001
        return f"De AI-analyse kon niet worden uitgevoerd: {exc}"


def build_prompt(question: str) -> str:
    context = build_context()
    analysis_data = build_ai_analysis_data()
    return f"""
{_system_prefix()}

## HUIDIGE CONTEXT
{json.dumps(context, ensure_ascii=False, separators=(",", ":"))}

## ANALYSEDATA
{json.dumps(analysis_data, ensure_ascii=False, separators=(",", ":"))}

## VRAAG
{question.strip()}

## ANTWOORDOPBOUW
Gebruik een passende korte structuur. Zet technische onderbouwing altijd onder:
### Technische details
""".strip()


def build_activity_comparison_prompt(comparison_context: dict, question: str) -> str:
    return f"""
{_system_prefix()}

## OPDRACHT
Vergelijk uitsluitend de 2 geselecteerde activiteiten. Dit is geen algemene trendanalyse.
De gebruiker kiest bewust deze 2 activiteiten. Andere historische activiteiten mogen niet worden gebruikt.
Benoem eerst de belangrijkste praktische verschillen en overeenkomsten.
Maak alleen een prestatie- of efficiëntievergelijking als beide activiteiten Running of TrailRun zijn en de beschikbare context dit verantwoord toelaat.
Als parcours, hoogte, temperatuur, wind, trainingsdoel of wedstrijdstatus ontbreken, vermeld dan dat dit de vergelijking begrenst.
Streamsamenvattingen beschrijven het verloop en zijn geen zelfstandig bewijs van sportieve kwaliteit.

## GESELECTEERDE ACTIVITEITEN EN CONTEXT
{json.dumps(comparison_context, ensure_ascii=False, separators=(",", ":"))}

## VRAAG VAN DE GEBRUIKER
{question.strip() or "Vergelijk deze 2 activiteiten praktisch en inhoudelijk."}

## ANTWOORDOPBOUW
#### Vergelijking
Maximaal 5 korte inzichten.

#### Praktische betekenis
Maximaal 3 concrete conclusies.

#### Wat weten we niet?
Alleen de belangrijkste ontbrekende context.

### Technische details
Gebruikte waarden, streamdekking, wellnesscontext, berekeningen en beperkingen.
""".strip()


def handle_message(question: str) -> str:
    if not question or not question.strip():
        return "Stel een concrete vraag over je training of herstel."
    return _run_ai(build_prompt(question))


def compare_activities_with_ai(comparison_context: dict, question: str = "") -> str:
    if not isinstance(comparison_context, dict) or not comparison_context:
        return "Er is geen geldige vergelijkingscontext beschikbaar."
    return _run_ai(build_activity_comparison_prompt(comparison_context, question))
