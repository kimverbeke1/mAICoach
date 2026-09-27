# -*- coding: utf-8 -*-
"""
MATCHFITAI_INSIGHT_PROMPT_DEDUP_2026-09-27 (op verzoek van Kim: "Genereer AI
inzichten duurde meer dan een minuut. Kan dat sneller en waar zit de
bottleneck?")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door de code van athlete_insight_generator.py en dit
bestand naast elkaar te leggen, en aangetoond met een representatieve
grootte-simulatie: ~50% kleinere prompt na de fix): athlete_insight_
generator.generate_athlete_insights() riep tot nu toe handle_message(
build_prompt()) aan, waarbij build_prompt() daar al een VOLLEDIGE, op
zichzelf staande prompt opbouwt (alle activiteiten + wellness-records,
compact, met strikte "enkel JSON"-instructies). Maar handle_message()
HIERONDER wrapt die tekst ALS "vraag" opnieuw in zijn EIGEN build_prompt(
question) - die daar NOGMAALS build_context() + build_ai_analysis_data()
(een aparte, overlappende compactie van dezelfde activiteiten/wellness-
bronnen) EN de volledige BASE_RULES aan toevoegt. Gevolg: de dataset werd
via 2 verschillende compactie-schema's DUBBEL meegestuurd, plus irrelevante/
tegenstrijdige instructies (BASE_RULES eist bv. "### Technische details"-
opmaak, terwijl athlete_insight_generator.py expliciet ENKEL geldige JSON
eist, zonder extra tekst) - dat verklaart zowel de trage duur (een pak meer
tokens dan nodig) als een verhoogd risico op niet-parsebare AI-antwoorden.
FIX (dit bestand): _run_ai() geeft nu geen intern geheim meer prijs - hij is
importeerbaar en accepteert een optionele reasoning_effort-parameter, zodat
athlete_insight_generator.py hem RECHTSTREEKS kan aanroepen met zijn EIGEN,
al complete prompt (geen tweede wrap meer nodig via handle_message/build_
prompt hier). Chat/Daily update blijven ongewijzigd - die roepen nog steeds
handle_message() aan zoals voorheen, dus hun gedrag is 100% behouden.
"""
import json
import os
from dotenv import load_dotenv
from AICoach.ai_analysis_data import build_ai_analysis_data
from AICoach.context_builder import build_context
load_dotenv(".env", override=True)
USE_REAL_AI = os.getenv("USE_REAL_AI", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
BASE_RULES = """
Je bent MatchFitAI, een persoonlijke sportcoach en sportdata-analist.
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
def _run_ai(prompt: str, reasoning_effort: str | None = None) -> str:
    """MATCHFITAI_INSIGHT_PROMPT_DEDUP_2026-09-27: nu ook rechtstreeks
    bruikbaar door andere modules (bv. athlete_insight_generator.py) die al
    een eigen, complete prompt opbouwen en dus NIET via build_prompt()
    hieronder gewrapt willen worden. `reasoning_effort` is optioneel (bv.
    "low") en wordt enkel doorgegeven aan de Responses API als expliciet
    meegegeven - bestaand gedrag (handle_message(), zonder deze parameter)
    blijft dus volledig ongewijzigd."""
    if not USE_REAL_AI:
        return (
            "De echte AI-call staat uit. Zet `USE_REAL_AI=true` in `.env` "
            "om deze analyse uit te voeren.\n\n### Technische details\n"
            "Er is geen externe AI-call uitgevoerd."
        )
    if not OPENAI_API_KEY:
        return "OPENAI_API_KEY ontbreekt in `.env`."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        kwargs = {"model": OPENAI_MODEL, "input": prompt}
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        response = client.responses.create(**kwargs)
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
        return "De AI gaf geen tekst terug."
    except Exception as exc:
        return f"De AI-analyse kon niet worden uitgevoerd: {exc}"
def build_prompt(question: str) -> str:
    context = build_context()
    analysis_data = build_ai_analysis_data()
    return f"""
{BASE_RULES}
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
{BASE_RULES}
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
