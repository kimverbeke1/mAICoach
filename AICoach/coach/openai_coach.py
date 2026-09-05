from pathlib import Path
import json
import os

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
HISTORY_DIR = ROOT / "data" / "history"
INSIGHTS_DIR = ROOT / "data" / "daily_insights"

load_dotenv(ENV_PATH, override=True)


def load_history():
    files = sorted(HISTORY_DIR.glob("*.json"))

    if not files:
        raise FileNotFoundError(
            f"Geen historiekbestanden gevonden in {HISTORY_DIR}"
        )

    history = []

    for history_file in files:
        with history_file.open("r", encoding="utf-8") as handle:
            record = json.load(handle)

        if isinstance(record, dict):
            record.setdefault("date", history_file.stem)
            history.append(record)

    history.sort(key=lambda item: str(item.get("date", "")))

    if not history:
        raise ValueError("Geen geldige historiekrecords gevonden")

    return history


def numeric_average(records, field):
    values = []

    for record in records:
        value = record.get(field)

        if value is None:
            continue

        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    if not values:
        return None

    return round(sum(values) / len(values), 1)


def calculate_form(fitness, fatigue):
    try:
        return round(float(fitness) - float(fatigue), 1)
    except (TypeError, ValueError):
        return None


def build_prompt(history):
    latest = history[-1]
    last_7 = history[-7:]
    last_30 = history[-30:]

    fitness = latest.get("fitness")
    fatigue = latest.get("fatigue")
    form = calculate_form(fitness, fatigue)

    return f"""
Je bent de persoonlijke endurance-trainingscoach van Kim.

Recentste datum: {latest.get("date")}

Huidige waarden:
- Fitness: {fitness}
- Fatigue: {fatigue}
- Vorm, berekend als fitness min fatigue: {form}
- Training load: {latest.get("training_load")}
- Rusthartslag: {latest.get("resting_hr")} bpm
- Gewicht: {latest.get("weight")} kg
- RPE: {latest.get("rpe")}
- Gevoel: {latest.get("feel")}

Gemiddelden over de laatste 7 records:
- Fitness: {numeric_average(last_7, "fitness")}
- Fatigue: {numeric_average(last_7, "fatigue")}
- Training load: {numeric_average(last_7, "training_load")}
- Rusthartslag: {numeric_average(last_7, "resting_hr")} bpm

Gemiddelden over de laatste 30 records:
- Fitness: {numeric_average(last_30, "fitness")}
- Fatigue: {numeric_average(last_30, "fatigue")}
- Training load: {numeric_average(last_30, "training_load")}
- Rusthartslag: {numeric_average(last_30, "resting_hr")} bpm

Schrijf in het Nederlands:
1. Een korte dagelijkse samenvatting.
2. Een herstelinschatting.
3. Een voorzichtig en concreet trainingsadvies voor vandaag of morgen.
4. Maximaal drie aandachtspunten.

Gebruik uitsluitend de aangeleverde waarden.
Maak geen medische diagnose.
Vermeld duidelijk wanneer gegevens ontbreken.
Beperk het antwoord tot maximaal 180 woorden.
""".strip()


def generate_advice(history):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise ValueError(
            f"OPENAI_API_KEY ontbreekt of is leeg in {ENV_PATH}"
        )

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model="gpt-5-mini",
        instructions=(
            "Je bent een voorzichtige en feitelijke endurancecoach. "
            "Geef compact, begrijpelijk en niet-medisch trainingsadvies."
        ),
        input=build_prompt(history),
    )

    advice = (response.output_text or "").strip()

    if not advice:
        raise RuntimeError("OpenAI gaf geen tekst terug")

    return advice


def save_insight(history, advice):
    date_key = str(history[-1].get("date") or "latest")[:10]

    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = INSIGHTS_DIR / f"{date_key}.json"

    payload = {
        "date": date_key,
        "model": "gpt-5-mini",
        "advice": advice,
    }

    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    return output_file


def main():
    print()
    print("=" * 60)
    print("MATCHFIT AI DAILY COACH")
    print("=" * 60)
    print()

    history = load_history()

    print(f"Historiekrecords: {len(history)}")
    print(f"Recentste datum: {history[-1].get('date')}")
    print("OpenAI wordt aangeroepen...")
    print()

    advice = generate_advice(history)
    output_file = save_insight(history, advice)

    print(advice)
    print()
    print(f"Opgeslagen in: {output_file}")
    print()


if __name__ == "__main__":
    main()
