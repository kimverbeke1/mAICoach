# -*- coding: utf-8 -*-
"""Laat GPT zelf inzichten ontdekken uit de volledige ruwe mAICoach-data.

Belangrijk uitgangspunt: dit script berekent GEEN conclusies vooraf. Het levert
uitsluitend de ruwe, compacte activiteiten- en wellnessdata aan het taalmodel.
Het model bekijkt die volledige data en zoekt zelf naar bruikbare, stuurbare
patronen. Tautologische vaststellingen (zoals "lagere hartslag bij gelijke
snelheid") worden expliciet uitgesloten, omdat die geen sturende actie opleveren.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from AICoach.chat.ai_message_handler import handle_message

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
INSIGHTS_FILE = ROOT / "data" / "athlete_insights.json"

# Ruwe velden die GPT nodig heeft om zelf te analyseren. Geen afgeleide of
# voorgekauwde conclusies; enkel gemeten data.
ACTIVITY_FIELDS = (
    "id", "start_date_local", "start_date", "name", "type", "distance",
    "moving_time", "elapsed_time", "average_heartrate", "max_heartrate",
    "icu_training_load", "hr_load", "pace_load", "trimp", "icu_intensity",
    "icu_ctl", "icu_atl", "icu_hr_zone_times", "pace_zone_times",
    "total_elevation_gain", "race", "average_cadence", "decoupling",
)
WELLNESS_FIELDS = (
    "id", "date", "restingHR", "hrv", "sleepSecs", "sleepScore",
    "sleepQuality", "readiness", "steps", "vo2max", "ctl", "atl",
    "ctlLoad", "atlLoad", "rampRate", "motivation", "mood", "fatigue",
)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def clean_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def compact_records(records: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    compact: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        item = {
            field: clean_value(record.get(field))
            for field in fields
            if record.get(field) is not None
        }
        if item:
            compact.append(item)
    return compact


def extract_json_object(text: str) -> dict[str, Any]:
    content = str(text or "").strip()
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:-1]).strip()
    first = content.find("{")
    last = content.rfind("}")
    if first < 0 or last <= first:
        raise ValueError("AI-antwoord bevat geen geldig JSON-object.")
    payload = json.loads(content[first : last + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI-antwoord heeft een onverwachte structuur.")
    return payload


def normalize_insights(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for insight in payload.get("insights", [])[:3]:
        if not isinstance(insight, dict):
            continue
        title = str(insight.get("title") or "").strip()
        meaning = str(insight.get("meaning") or "").strip()
        if not title or not meaning:
            continue
        normalized.append({
            "title": title,
            "meaning": meaning,
            "actionable_advice": str(insight.get("actionable_advice") or "").strip(),
            "confidence": str(insight.get("confidence") or "onvoldoende").strip(),
            "sample_size": insight.get("sample_size"),
            "sport_or_cluster": str(insight.get("sport_or_cluster") or "Algemeen").strip(),
            "evidence": [str(value) for value in insight.get("evidence", [])[:4]],
            "limitations": [str(value) for value in insight.get("limitations", [])[:3]],
            "supporting_dates": [str(value) for value in insight.get("supporting_dates", [])[:8]],
            "status": str(insight.get("status") or "voorlopige hypothese").strip(),
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": str(
            payload.get("headline")
            or "mAICoach vond nog geen voldoende sterk patroon."
        ).strip(),
        "insights": normalized,
        "next_focus": str(payload.get("next_focus") or "Meer vergelijkbare sessies verzamelen.").strip(),
    }


def build_prompt() -> str:
    activities = compact_records(load_json(ACTIVITIES_FILE, []), ACTIVITY_FIELDS)
    wellness = compact_records(load_json(WELLNESS_FILE, []), WELLNESS_FIELDS)

    dataset = {
        "activities": activities,
        "wellness": wellness,
        "counts": {
            "activities": len(activities),
            "wellness_days": len(wellness),
        },
    }

    return f"""
Je bent mAICoach en analyseert zelf de volledige ruwe data van de atleet.
Er zijn GEEN voorberekende conclusies meegegeven. Jij ontdekt de patronen.

DOEL
- Zoek patronen die de atleet praktisch kan STUREN of gebruiken om beter te trainen en te herstellen.
- Focus op factoren die de atleet vooraf kan beïnvloeden of opvolgen, bijvoorbeeld:
  slaap en slaapscore de nacht ervoor, HRV, rusthartslag, readiness, en de stand
  van Form (TSB), Fitness (CTL) en Fatigue (ATL) op de dag van een sessie.
- Onderzoek wanneer de atleet relatief goed of minder goed presteert binnen
  vergelijkbare activiteiten, en welke herstel- of belastingscontext daarbij hoort.

VERBODEN CONCLUSIES
- Geef GEEN tautologische vaststellingen. Verboden voorbeeld: "lagere hartslag bij
  gelijke snelheid is beter". Dat is per definitie waar en levert geen stuurbare actie op.
- Leid geen prestatie af uit een maat die je zelf uit die prestatie hebt gedefinieerd.
- Trek prestatie- of efficiëntieconclusies uitsluitend voor Running en TrailRun.
- Voor Padel en Badminton beoordeel je alleen fysiologische belasting en herstelcontext,
  nooit speelkwaliteit, winst of verlies.

HARDE REGELS
- Elk inzicht moet een concrete, stuurbare betekenis hebben: wat kan de atleet hiermee doen?
- Gebruik de huidige Intervals-stressparameter niet.
- Behandel ontbrekende waarden nooit als nul.
- Hoogtemeting kan fout zijn en mag geen sterke verklaring zijn zonder consistente data.
- Noem looptechniek, weer of parcours alleen als er expliciete data voor is.
- Combineer overlappende signalen (Form, Fatigue, readiness, slaap) tot één helder inzicht.
- Herhaal hetzelfde inzicht niet in andere bewoordingen.
- Maximaal 3 unieke inzichten. Bij onvoldoende bewijs geef je er minder.
- Persoonlijke patronen zijn hypotheses en moeten bij nieuwe data opnieuw getoetst worden.
- De hoofdtekst is kort, praktisch en zonder percentages. Cijfers horen alleen in evidence.

Geef uitsluitend geldig JSON in deze vorm:
{{
  "headline": "één korte hoofdconclusie",
  "insights": [
    {{
      "title": "maximaal 8 woorden",
      "meaning": "maximaal 2 korte zinnen in gewone taal",
      "actionable_advice": "één concrete, stuurbare actie of opvolging",
      "confidence": "hoog|redelijk|middelmatig|laag|onvoldoende",
      "sample_size": 0,
      "sport_or_cluster": "bijvoorbeeld TrailRun 15-18 km",
      "evidence": ["maximaal 4 korte technische bewijsregels"],
      "limitations": ["maximaal 3 beperkingen"],
      "supporting_dates": ["YYYY-MM-DD"],
      "status": "voorlopige hypothese"
    }}
  ],
  "next_focus": "één korte zin over welk nieuw bewijs het nuttigst is"
}}

DATASET
{json.dumps(dataset, ensure_ascii=False, separators=(',', ':'))}
""".strip()


def generate_athlete_insights() -> dict[str, Any]:
    answer = handle_message(build_prompt())
    insights = normalize_insights(extract_json_object(answer))
    INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = INSIGHTS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(INSIGHTS_FILE)
    return {
        "insights_file": str(INSIGHTS_FILE.relative_to(ROOT)),
        "insight_count": len(insights["insights"]),
        "headline": insights["headline"],
    }


def main() -> None:
    print(json.dumps(generate_athlete_insights(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
